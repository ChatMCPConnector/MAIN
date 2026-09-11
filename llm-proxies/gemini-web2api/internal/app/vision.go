package app

import (
	"encoding/base64"
	"fmt"
	"io"
	"net/http"
	"strings"

	fhttp "github.com/bogdanfinn/fhttp"
)

// Image / video reading: upload the client-supplied image or video as an attachment, then reference it in the conversation.
//
// Login-only — anonymous can upload the file, but referencing it gets 1100 from the server.
// Attachment kind bit: 1=image, 2=video, 3=text file; shared by upload and reference (see the file tuple in gemini.go).
// Video, observed in practice (packet capture): same resumable upload, file tuple's 2nd slot set to 2, mime video/mp4 —
// the model reads the video content (replied "this is a short clip with an icon animation").

// Size cap for a single image. The upstream gives no explicit number; pick a value that covers normal
// screenshots without dragging a request out too long. Over the cap: error out instead of uploading anyway — a server-side rejection is harder to read.
const maxImageBytes = 12 * 1024 * 1024

// Size cap for video. Video is base64-embedded into the JSON request body, so too large a value drags a request out; pick a
// value that covers common short clips without hanging the request. Over the cap: error out.
const maxVideoBytes = 50 * 1024 * 1024

// pendingUpload is an attachment not yet uploaded. The real upload must wait until the account and egress are picked,
// so it is carried along as-is between the handler and streamGenerate.
type pendingUpload struct {
	Data []byte
	Name string
	Mime string
	Kind int // 1=image, 2=video, 3=text/plain file
}

// collectImages extracts the images from OpenAI-format messages.
//
// Two forms are recognized: image_url in the content array (OpenAI Chat) and input_image (Responses).
// Sources support data URLs and http(s) links; the latter are downloaded and then uploaded — passing the link
// to the upstream directly doesn't work, it only recognizes attachments in its own storage.
func collectImages(messages []map[string]interface{}, proxyURL string) ([]pendingUpload, error) {
	var out []pendingUpload
	for _, m := range messages {
		parts, ok := m["content"].([]interface{})
		if !ok {
			continue
		}
		for _, c := range parts {
			cm, ok := c.(map[string]interface{})
			if !ok {
				continue
			}
			var src string
			switch getStr(cm, "type") {
			case "image_url":
				if iu, ok := cm["image_url"].(map[string]interface{}); ok {
					src = getStr(iu, "url")
				} else {
					src = getStr(cm, "image_url")
				}
			case "input_image":
				src = firstNonEmpty(getStr(cm, "image_url"), getStr(cm, "url"), getStr(cm, "data"))
			case "video_url":
				if vu, ok := cm["video_url"].(map[string]interface{}); ok {
					src = getStr(vu, "url")
				} else {
					src = getStr(cm, "video_url")
				}
			case "input_video":
				src = firstNonEmpty(getStr(cm, "video_url"), getStr(cm, "url"), getStr(cm, "data"))
			default:
				continue
			}
			if strings.TrimSpace(src) == "" {
				continue
			}
			img, err := materializeImage(src, proxyURL, len(out)+1)
			if err != nil {
				return nil, err
			}
			out = append(out, img)
		}
	}
	return out, nil
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}

// materializeImage turns an image source into bytes ready for upload.
func materializeImage(src, proxyURL string, idx int) (pendingUpload, error) {
	if strings.HasPrefix(src, "data:") {
		return decodeDataURL(src, idx)
	}
	if strings.HasPrefix(src, "http://") || strings.HasPrefix(src, "https://") {
		return fetchImage(src, proxyURL, idx)
	}
	return pendingUpload{}, fmt.Errorf("image %d: unsupported source (want a data: URL or http(s) link)", idx)
}

// decodeDataURL parses data:<mime>;base64,<payload>.
func decodeDataURL(src string, idx int) (pendingUpload, error) {
	comma := strings.Index(src, ",")
	if comma < 0 {
		return pendingUpload{}, fmt.Errorf("image %d: malformed data URL", idx)
	}
	meta, payload := src[5:comma], src[comma+1:]
	mime := "image/png"
	if i := strings.Index(meta, ";"); i > 0 {
		mime = meta[:i]
	} else if meta != "" {
		mime = meta
	}
	var data []byte
	var err error
	if strings.Contains(meta, "base64") {
		data, err = base64.StdEncoding.DecodeString(payload)
	} else {
		data = []byte(payload)
	}
	if err != nil {
		return pendingUpload{}, fmt.Errorf("image %d: bad base64: %w", idx, err)
	}
	return newMediaUpload(data, mime, idx)
}

// fetchImage downloads a remote image through the same egress as the real request: pulling the image from another IP
// and sending the conversation from this one has no benefit beyond being slower, and exposes one more egress.
func fetchImage(src, proxyURL string, idx int) (pendingUpload, error) {
	var body []byte
	var ctype string
	if proxyURL != "" {
		req, err := http.NewRequest("GET", src, nil)
		if err != nil {
			return pendingUpload{}, err
		}
		applyChromeHeaders(req)
		resp, err := getStdlibClient(proxyURL).Do(req)
		if err != nil {
			return pendingUpload{}, fmt.Errorf("image %d: fetch failed: %w", idx, err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != 200 {
			return pendingUpload{}, fmt.Errorf("image %d: fetch returned HTTP %d", idx, resp.StatusCode)
		}
		ctype = resp.Header.Get("Content-Type")
		body, err = io.ReadAll(io.LimitReader(resp.Body, maxImageBytes+1))
		if err != nil {
			return pendingUpload{}, err
		}
	} else {
		req, err := fhttp.NewRequest("GET", src, nil)
		if err != nil {
			return pendingUpload{}, err
		}
		resp, err := getTLSClient().Do(req)
		if err != nil {
			return pendingUpload{}, fmt.Errorf("image %d: fetch failed: %w", idx, err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != 200 {
			return pendingUpload{}, fmt.Errorf("image %d: fetch returned HTTP %d", idx, resp.StatusCode)
		}
		ctype = resp.Header.Get("Content-Type")
		body, err = io.ReadAll(io.LimitReader(resp.Body, maxImageBytes+1))
		if err != nil {
			return pendingUpload{}, err
		}
	}
	if i := strings.Index(ctype, ";"); i > 0 {
		ctype = ctype[:i]
	}
	if !strings.HasPrefix(ctype, "image/") && !strings.HasPrefix(ctype, "video/") {
		ctype = "image/png"
	}
	return newMediaUpload(body, ctype, idx)
}

// newMediaUpload decides image vs video by mime:
//   - video/* → attachment kind bit 2 (matching the packet capture: file tuple [path,2,null,"video/mp4"]), capped at maxVideoBytes;
//   - everything else treated as image → kind bit 1, capped at maxImageBytes.
// The kind bit 1/2 is the server's switch for the media type; a wrong value makes the model parse the attachment as the wrong type.
func newMediaUpload(data []byte, mime string, idx int) (pendingUpload, error) {
	if len(data) == 0 {
		return pendingUpload{}, fmt.Errorf("media %d: empty", idx)
	}
	if strings.HasPrefix(mime, "video/") {
		if len(data) > maxVideoBytes {
			return pendingUpload{}, fmt.Errorf("video %d: %d bytes exceeds the %d-byte limit",
				idx, len(data), maxVideoBytes)
		}
		return pendingUpload{
			Data: data, Mime: mime, Kind: 2,
			Name: fmt.Sprintf("video%d%s", idx, mediaExt(mime)),
		}, nil
	}
	if len(data) > maxImageBytes {
		return pendingUpload{}, fmt.Errorf("image %d: %d bytes exceeds the %d-byte limit",
			idx, len(data), maxImageBytes)
	}
	return pendingUpload{
		Data: data, Mime: mime, Kind: 1,
		Name: fmt.Sprintf("image%d%s", idx, mediaExt(mime)),
	}, nil
}

// mediaExt returns an extension by mime. The filename is shown to the model, and a mismatched extension easily misleads it.
func mediaExt(mime string) string {
	switch mime {
	case "image/jpeg", "image/jpg":
		return ".jpg"
	case "image/webp":
		return ".webp"
	case "image/gif":
		return ".gif"
	case "image/heic":
		return ".heic"
	case "video/mp4":
		return ".mp4"
	case "video/webm":
		return ".webm"
	case "video/quicktime":
		return ".mov"
	default:
		if strings.HasPrefix(mime, "video/") {
			return ".mp4"
		}
		return ".png"
	}
}
