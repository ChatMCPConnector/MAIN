package main

import (
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"sync"
)

var (
	redirectCode string
	redirectState string
	mu sync.Mutex
	serverReady = make(chan struct{})
)

func handleCallback(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	defer mu.Unlock()

	query := r.URL.Query()
	redirectCode = query.Get("code")
	redirectState = query.Get("state")

	log.Printf("Received callback - Code: %s, State: %s", redirectCode[:min(20, len(redirectCode))]+"...", redirectState)

	// Send success response to browser
	w.Header().Set("Content-Type", "text/html")
	fmt.Fprintf(w, `<html><body><h2>✓ Authentication successful!</h2><p>You can close this tab and return to the terminal.</p></body></html>`)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func startCallbackServer(port string) *http.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/oauth-callback", handleCallback)

	srv := &http.Server{
		Addr:    ":" + port,
		Handler: mux,
	}

	go func() {
		close(serverReady)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("Server error: %v", err)
		}
	}()

	return srv
}

func runAuthHelper(oauthURL string, verifier, challenge string) error {
	// Wait a bit for the user to complete OAuth
	fmt.Println("\nWaiting for OAuth callback...")
	fmt.Println("(The code from the browser redirect will be captured automatically)")

	// Poll for the redirect code
	for i := 0; i < 120; i++ { // Wait up to 2 minutes
		mu.Lock()
		code := redirectCode
		state := redirectState
		mu.Unlock()

		if code != "" {
			log.Printf("Got OAuth code, exchanging for tokens...")

			// Now run the Go auth helper with the code
			cmd := exec.Command("go", "run", "./cmd/auth", "--manual-code", code)
			cmd.Dir = "/workspaces/dvcrn-antigravity-oauth-proxy"
			cmd.Env = append(os.Environ(), "PATH=/usr/local/go/bin:$PATH")

			output, err := cmd.CombinedOutput()
			if err != nil {
				return fmt.Errorf("auth helper failed: %w\nOutput: %s", err, string(output))
			}

			log.Printf("Auth helper output: %s", string(output))
			return nil
		}

		time.Sleep(1 * time.Second)
	}

	return fmt.Errorf("timeout waiting for OAuth callback")
}

func main() {
	// Check if running in manual code mode
	if len(os.Args) > 1 && os.Args[1] == "--manual-code" {
		// This mode is for internal use only - we just print what we got
		if len(os.Args) > 2 {
			fmt.Printf("Manual code received: %s\n", os.Args[2])
			return
		}
	}
	// Start callback server on port 51121
	srv := startCallbackServer("51121")
	<-serverReady
	fmt.Println("✓ Callback server started on port 51121")

	// Generate OAuth state and PKCE verifier
	state := fmt.Sprintf("%d", time.Now().UnixNano())
	verifier := generateRandomString(128)
	challenge := hashSHA256(verifier)

	// Build OAuth URL
	oauthURL := fmt.Sprintf(
		"https://accounts.google.com/o/oauth2/v2/auth?access_type=offline"+
			"&client_id=1071006060591-tmhssin2h21lcre2"+"35vtolojh4g403ep.apps.googleusercontent.com"+
			"&code_challenge=%s"+
			"&code_challenge_method=S256"+
			"&include_granted_scopes=true"+
			"&prompt=consent"+
			"&redirect_uri=http%%3A%%2F%%2Flocalhost%%3A51121%%2Foauth-callback"+
			"&response_type=code"+
			"&scope=https%%3A%%2F%%2Fwww.googleapis.com%%2Fauth%%2Fcloud-platform+https%%3A%%2F%%2Fwww.googleapis.com%%2Fauth%%2Fuserinfo.email+https%%3A%%2F%%2Fwww.googleapis.com%%2Fauth%%2Fuserinfo.profile+https%%3A%%2F%%2Fwww.googleapis.com%%2Fauth%%2Fcclog+https%%3A%%2F%%2Fwww.googleapis.com%%2Fauth%%2Fexperimentsandconfigs"+
			"&state=%s",
		challenge, state,
	)

	fmt.Println("\n" + strings.Repeat("=", 70))
	fmt.Println("🌐 Open this URL in your browser:")
	fmt.Println(strings.Repeat("=", 70))
	fmt.Println("\n" + oauthURL + "\n")
	fmt.Println(strings.Repeat("=", 70))

	// Try to open browser automatically
	if err := openBrowser(oauthURL); err != nil {
		fmt.Printf("Could not open browser automatically: %v\n", err)
	}

	// Run auth helper and wait for callback
	if err := runAuthHelper(oauthURL, verifier, challenge); err != nil {
		log.Fatalf("Auth failed: %v", err)
	}

	// Shutdown server
	if err := srv.Shutdown(context.Background()); err != nil {
		log.Printf("Server shutdown error: %v", err)
	}

	fmt.Println("\n✅ OAuth setup complete!")
}

func generateRandomString(length int) string {
	b := make([]byte, length)
	rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

func hashSHA256(s string) string {
	h := sha256.Sum256([]byte(s))
	return base64.RawURLEncoding.EncodeToString(h[:])
}

func openBrowser(url string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", url)
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	return cmd.Start()
}