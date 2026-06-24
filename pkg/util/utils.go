package ten_ai_base

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"strings"
)

var DefaultHeaderKeys = []string{"authorization", "api-key", "x-api-key", "xi-api-key"}

var DefaultJSONKeys = []string{
	"accesskey",
	"apikey",
	"appkey",
	"authorization",
	"key",
	"secret",
	"secretid",
	"secretkey",
	"ststoken",
	"token",
	"vendorkey",
	"vendorsecret",
}

func maskDefault(value string) string {
	if value == "" {
		return value
	}
	runes := []rune(value)
	step := len(runes) / 5
	if step <= 0 {
		return value
	}
	if step > 5 {
		step = 5
	}
	sum := sha256.Sum256([]byte(value))
	fingerprint := fmt.Sprintf("%x", sum[:4])
	return string(runes[:step]) + "..." + string(runes[len(runes)-step:]) + "#" + fingerprint
}

func MaskSecret(value string) string {
	return maskDefault(value)
}

func Encrypt(value string) string {
	return MaskSecret(value)
}

func RedactHeaders(headers map[string]string, headerKeys ...[]string) map[string]string {
	if headers == nil {
		return nil
	}
	if len(headers) == 0 {
		return map[string]string{}
	}

	var effectiveHeaderKeys []string
	if len(headerKeys) > 0 {
		effectiveHeaderKeys = headerKeys[0]
	}
	if effectiveHeaderKeys == nil {
		effectiveHeaderKeys = DefaultHeaderKeys
	}
	normalizedHeaderKeys := make(map[string]struct{}, len(effectiveHeaderKeys))
	for _, key := range effectiveHeaderKeys {
		normalizedHeaderKeys[strings.ToLower(key)] = struct{}{}
	}

	redacted := make(map[string]string, len(headers))
	for key, value := range headers {
		if _, ok := normalizedHeaderKeys[strings.ToLower(key)]; ok {
			redacted[key] = MaskSecret(value)
			continue
		}
		redacted[key] = value
	}
	return redacted
}

func RedactJSON(v any, jsonKeys ...[]string) (any, error) {
	rawData, err := json.Marshal(v)
	if err != nil {
		return nil, err
	}

	var normalized any
	if err := json.Unmarshal(rawData, &normalized); err != nil {
		return nil, err
	}

	var effectiveJSONKeys []string
	if len(jsonKeys) > 0 {
		effectiveJSONKeys = jsonKeys[0]
	}
	if effectiveJSONKeys == nil {
		effectiveJSONKeys = DefaultJSONKeys
	}

	return redactJSONValue(normalized, normalizedJSONKeys(effectiveJSONKeys)), nil
}

func redactJSONValue(value any, normalizedKeys map[string]struct{}) any {
	switch typed := value.(type) {
	case map[string]any:
		redacted := make(map[string]any, len(typed))
		for key, item := range typed {
			if isSensitiveKey(key, normalizedKeys) {
				redacted[key] = redactValue(item, normalizedKeys)
				continue
			}
			redacted[key] = redactJSONValue(item, normalizedKeys)
		}
		return redacted
	case []any:
		redacted := make([]any, len(typed))
		for i, item := range typed {
			redacted[i] = redactJSONValue(item, normalizedKeys)
		}
		return redacted
	default:
		return value
	}
}

func normalizedJSONKeys(jsonKeys []string) map[string]struct{} {
	normalized := make(map[string]struct{}, len(jsonKeys))
	for _, key := range jsonKeys {
		normalized[normalizeKey(key)] = struct{}{}
	}
	return normalized
}

func normalizeKey(key string) string {
	var builder strings.Builder
	builder.Grow(len(key))
	for _, ch := range key {
		switch {
		case ch >= 'a' && ch <= 'z':
			builder.WriteRune(ch)
		case ch >= 'A' && ch <= 'Z':
			builder.WriteRune(ch + ('a' - 'A'))
		case ch >= '0' && ch <= '9':
			builder.WriteRune(ch)
		}
	}
	return builder.String()
}

func isSensitiveKey(key string, normalizedKeys map[string]struct{}) bool {
	normalized := normalizeKey(key)
	if _, ok := normalizedKeys[normalized]; ok {
		return true
	}
	for item := range normalizedKeys {
		if strings.Contains(normalized, item) {
			return true
		}
	}
	return false
}

func redactValue(value any, normalizedKeys map[string]struct{}) any {
	switch typed := value.(type) {
	case nil:
		return nil
	case string:
		return MaskSecret(typed)
	case []any:
		redacted := make([]any, len(typed))
		for i, item := range typed {
			redacted[i] = redactJSONValue(item, normalizedKeys)
		}
		return redacted
	case map[string]any:
		redacted := make(map[string]any, len(typed))
		for key, item := range typed {
			redacted[key] = redactJSONValue(item, normalizedKeys)
		}
		return redacted
	default:
		return MaskSecret(fmt.Sprint(value))
	}
}
