package app

import (
	"fmt"
	"os"
	"sync"

	"github.com/pkoukk/tiktoken-go"
)

// tiktoken cl100k_base — GPT-4 BPE. Google hasn't published Gemini's real tokenizer,
// but at the BPE level the rules are similar, and it's far more accurate than chars/4
// for mixed Chinese/English (measured: within ±20% for Chinese).
//
// Loaded into memory once (~5MB); each Encode afterwards is ~microseconds.
var (
	tokenizer     *tiktoken.Tiktoken
	tokenizerOnce sync.Once
	tokenizerOK   bool
)

func initTokenizer() {
	tokenizerOnce.Do(func() {
		// tiktoken-go downloads cl100k_base.tiktoken (~3MB) from a remote host on first
		// load, caching it in ${TIKTOKEN_CACHE_DIR} or ${HOME}/.cache/tiktoken.
		// For docker images, pre-caching during docker build is recommended.
		t, err := tiktoken.GetEncoding("cl100k_base")
		if err != nil {
			fmt.Fprintf(os.Stderr, "[tokenizer] init failed (will fall back to chars/4): %v\n", err)
			return
		}
		tokenizer = t
		tokenizerOK = true
	})
}

// countTokens returns the approximate token count of a text.
// Falls back to the chars/4 estimate when the tokenizer failed to load.
func countTokens(s string) int {
	if !tokenizerOK || tokenizer == nil {
		return len(s) / 4
	}
	return len(tokenizer.Encode(s, nil, nil))
}
