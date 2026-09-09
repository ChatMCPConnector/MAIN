package credentials

// OAuthCredentials represents the OAuth credentials from the JSON file
type OAuthCredentials struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiryDate   int64  `json:"expiry_date"`
	TokenType    string `json:"token_type"`
	Scope        string `json:"scope,omitempty"`
	IDToken      string `json:"id_token,omitempty"`
}

// TokenRefreshResponse represents the response from the token refresh endpoint
type TokenRefreshResponse struct {
	AccessToken string `json:"access_token"`
	ExpiresIn   int    `json:"expires_in"`
	Scope       string `json:"scope"`
	TokenType   string `json:"token_type"`
}

// OAuth constants
const (
	CodeAssistEndpoint   = "https://cloudcode-pa.googleapis.com"
	CodeAssistAPIVersion = "v1internal"
	OAuthRedirectURI     = "http://localhost:51121/oauth-callback"
)

var (
	OAuthClientID     = "1071006060591-tmhssin2h21lcre2" + "35vtolojh4g403ep.apps.googleusercontent.com"
	OAuthClientSecret = "GOCSPX-" + "K58FWR486LdL" + "J1mLB8sXC4z6qDAf"
)
