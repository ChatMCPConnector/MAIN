package app

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"

	fhttp "github.com/bogdanfinn/fhttp"
)

// Two-step resumable upload, matching the browser packet capture. A single-shot
// multipart POST to content-push.googleapis.com also exists (it works too); the
// two-step flow was chosen only to mirror the browser.
const uploadHost = "https://push.clients6.google.com/upload/"

// uploadBytes uploads bytes and returns the reference path (like /contrib_service/ttl_1d/…). No mime on upload.
//
// Anonymous uploads succeed too, but referencing the uploaded file in a conversation
// returns 1100, so callers must ensure a cookie is present.
// proxyURL must use the same egress as the main request, otherwise Google sees two
// sessions sharing one file.
func uploadBytes(cookie, proxyURL string, data []byte, filename string) (string, error) {
	pushID, pctx, err := getUploadTokens(cookie, proxyURL)
	if err != nil {
		return "", fmt.Errorf("取上传页面参数失败: %w", err)
	}
	if pushID == "" {
		return "", fmt.Errorf("页面里没有 push_id，无法上传")
	}

	base := map[string]string{
		"Origin":         "https://gemini.google.com",
		"Referer":        "https://gemini.google.com/",
		"X-Tenant-Id":    "bard-storage",
		"Push-ID":        pushID,
		"Accept":         "*/*",
		"Sec-Fetch-Site": "same-site",
		"Sec-Fetch-Mode": "cors",
		"Sec-Fetch-Dest": "empty",
	}
	if pctx != "" {
		base["X-Client-Pctx"] = pctx
	}
	if cookie != "" {
		base["Cookie"] = cookie
	}
	with := func(extra map[string]string) map[string]string {
		h := make(map[string]string, len(base)+len(extra))
		for k, v := range base {
			h[k] = v
		}
		for k, v := range extra {
			h[k] = v
		}
		return h
	}

	// start fetches a one-time upload URL. The body is plain text "File name: xxx" —
	// even though Content-Type says urlencoded, don't infer the body shape from it.
	startHeaders := with(map[string]string{
		"Content-Type":                        "application/x-www-form-urlencoded;charset=UTF-8",
		"X-Goog-Upload-Command":               "start",
		"X-Goog-Upload-Protocol":              "resumable",
		"X-Goog-Upload-Header-Content-Length": strconv.Itoa(len(data)),
	})
	status, respHead, body, err := uploadPost(uploadHost, startHeaders,
		[]byte("File name: "+sanitizeUploadName(filename)), proxyURL)
	if err != nil {
		return "", fmt.Errorf("上传 start 失败: %w", err)
	}
	if status != 200 {
		return "", fmt.Errorf("上传 start 返回 HTTP %d: %s", status, truncate(string(body), 160))
	}
	putURL := respHead["x-goog-upload-url"]
	if putURL == "" {
		return "", fmt.Errorf("上传 start 没返回 x-goog-upload-url")
	}

	// send the bytes and finalize
	upHeaders := with(map[string]string{
		"Content-Type":          "application/x-www-form-urlencoded;charset=utf-8",
		"X-Goog-Upload-Command": "upload, finalize",
		"X-Goog-Upload-Offset":  "0",
	})
	status, _, body, err = uploadPost(putURL, upHeaders, data, proxyURL)
	if err != nil {
		return "", fmt.Errorf("上传 finalize 失败: %w", err)
	}
	if status != 200 {
		return "", fmt.Errorf("上传 finalize 返回 HTTP %d: %s", status, truncate(string(body), 160))
	}
	// The response body is the reference path. If it doesn't start with "/", we got an
	// error page; putting it into the payload may not fail server-side, but the model
	// sees an empty attachment.
	ref := strings.TrimSpace(string(body))
	if !strings.HasPrefix(ref, "/") {
		return "", fmt.Errorf("上传返回的不是引用路径: %s", truncate(ref, 160))
	}
	return ref, nil
}

// sanitizeUploadName strips characters that would break the request body — the filename goes verbatim into the start body.
func sanitizeUploadName(name string) string {
	name = strings.TrimSpace(name)
	if name == "" {
		return "upload.bin"
	}
	return strings.NewReplacer("\r", "", "\n", "").Replace(name)
}

// uploadPost POSTs through the same egress as the main request and returns the response headers too (start needs x-goog-upload-url).
func uploadPost(url string, headers map[string]string, body []byte, proxyURL string) (
	int, map[string]string, []byte, error) {
	if proxyURL != "" {
		req, err := http.NewRequest("POST", url, bytes.NewReader(body))
		if err != nil {
			return 0, nil, nil, err
		}
		applyChromeHeaders(req)
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		resp, err := getStdlibClient(proxyURL).Do(req)
		if err != nil {
			return 0, nil, nil, err
		}
		defer resp.Body.Close()
		b, err := io.ReadAll(resp.Body)
		h := map[string]string{}
		for k := range resp.Header {
			h[strings.ToLower(k)] = resp.Header.Get(k)
		}
		return resp.StatusCode, h, b, err
	}
	req, err := fhttp.NewRequest("POST", url, bytes.NewReader(body))
	if err != nil {
		return 0, nil, nil, err
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := getTLSClient().Do(req)
	if err != nil {
		return 0, nil, nil, err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	h := map[string]string{}
	for k := range resp.Header {
		h[strings.ToLower(k)] = resp.Header.Get(k)
	}
	return resp.StatusCode, h, b, err
}
