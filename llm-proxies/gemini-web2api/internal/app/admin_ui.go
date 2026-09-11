package app

import (
	"embed"
	"io/fs"
	"net/http"
)

//go:embed admin_ui/*
var adminUIFS embed.FS

func handleAdminUI(w http.ResponseWriter, r *http.Request) {
	sub, err := fs.Sub(adminUIFS, "admin_ui")
	if err != nil {
		http.Error(w, "embed error", 500)
		return
	}
	// All URLs inside the panel are relative so that it also works under a reverse
	// proxy sub-path (example.com/gemini/admin). Relative URLs resolve against the
	// **directory of the document URL**, so /admin and /admin/ resolve differently —
	// the former's directory is one level up. Normalize by redirecting to the
	// slash-terminated form.
	//
	// Location must be a relative value: writing "/admin/" would make the browser
	// jump to the site root's /admin/ behind a reverse proxy, losing the /gemini
	// prefix. http.Redirect is deliberately not used here — it expands the relative
	// target into an absolute path based on the request path, which would destroy
	// exactly that.
	path := r.URL.Path
	if path == "/admin" {
		w.Header().Set("Location", "admin/")
		w.WriteHeader(http.StatusMovedPermanently)
		return
	}
	if path == "/admin/" {
		path = "index.html"
	} else {
		path = path[len("/admin/"):]
	}
	f, err := sub.Open(path)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	stat, _ := f.Stat()
	data := make([]byte, stat.Size())
	f.Read(data)
	switch {
	case len(path) > 5 && path[len(path)-5:] == ".html":
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
	case len(path) > 3 && path[len(path)-3:] == ".js":
		w.Header().Set("Content-Type", "application/javascript")
	case len(path) > 4 && path[len(path)-4:] == ".css":
		w.Header().Set("Content-Type", "text/css")
	default:
		w.Header().Set("Content-Type", "application/octet-stream")
	}
	w.Write(data)
}
