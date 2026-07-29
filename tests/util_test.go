package ten_ai_base_test

import (
	"strings"
	"testing"

	ten_ai_base "github.com/TEN-framework/ten_ai_base/pkg/util"
)

func TestMaskSecret(t *testing.T) {
	t.Run("masks long values", func(t *testing.T) {
		if got := ten_ai_base.MaskSecret("1234567890"); got != "12...90#c775e7b7" {
			t.Fatalf("MaskSecret() = %q, want %q", got, "12...90#c775e7b7")
		}
		if got := ten_ai_base.MaskSecret("abcdefghijklmnopqrstuvwxyz"); got != "abcde...vwxyz#71c480df" {
			t.Fatalf("MaskSecret() = %q, want %q", got, "abcde...vwxyz#71c480df")
		}
	})

	t.Run("keeps short values", func(t *testing.T) {
		if got := ten_ai_base.MaskSecret(""); got != "" {
			t.Fatalf("MaskSecret() = %q, want empty string", got)
		}
		if got := ten_ai_base.MaskSecret("a"); got != "a" {
			t.Fatalf("MaskSecret() = %q, want %q", got, "a")
		}
		if got := ten_ai_base.MaskSecret("ab"); got != "ab" {
			t.Fatalf("MaskSecret() = %q, want %q", got, "ab")
		}
		if got := ten_ai_base.MaskSecret("张"); got != "张" {
			t.Fatalf("MaskSecret() = %q, want %q", got, "张")
		}
		if got := ten_ai_base.MaskSecret("abcd"); got != "abcd" {
			t.Fatalf("MaskSecret() = %q, want %q", got, "abcd")
		}
	})

	t.Run("supports modes", func(t *testing.T) {
		cases := map[string]string{
			"13800138000":        "13...00#a6942f97",
			"+8613800138000":     "+8...00#ec61f3c6",
			"alice@example.com":  "ali...com#ff8d9819",
			"a@example.com":      "a@...om#08168cd8",
			"110101199001011234": "110...234#04e7358a",
			"192.168.10.23":      "19...23#85512b03",
		}
		for value, want := range cases {
			if got := ten_ai_base.MaskSecret(value); got != want {
				t.Fatalf("MaskSecret(%q) = %q, want %q", value, got, want)
			}
		}
	})

	t.Run("default mode has fingerprint", func(t *testing.T) {
		got := ten_ai_base.MaskSecret("Bearer abcdef123456")
		if !strings.HasPrefix(got, "Bea...456#") {
			t.Fatalf("MaskSecret() = %q", got)
		}
		parts := strings.SplitN(got, "#", 2)
		if len(parts) != 2 || len(parts[1]) != 8 {
			t.Fatalf("MaskSecret() fingerprint = %q", got)
		}
	})

	t.Run("does not mask its own output twice", func(t *testing.T) {
		values := []string{
			"abcde",
			"abcdef123456",
			"abcdefghijklmnopqrstuvwxyz",
			"密钥abcdef123456",
		}
		for _, value := range values {
			masked := ten_ai_base.MaskSecret(value)
			if got := ten_ai_base.MaskSecret(masked); got != masked {
				t.Fatalf("MaskSecret(MaskSecret(%q)) = %q, want %q", value, got, masked)
			}
		}
	})
}

func BenchmarkMaskSecret(b *testing.B) {
	for i := 0; i < b.N; i++ {
		ten_ai_base.MaskSecret("Bearer abcdef1234567890")
	}
}

func TestDefaultKeys(t *testing.T) {
	if len(ten_ai_base.DefaultHeaderKeys) == 0 || len(ten_ai_base.DefaultJSONKeys) == 0 {
		t.Fatal("default key sets should not be empty")
	}

	jsonKeySet := make(map[string]struct{}, len(ten_ai_base.DefaultJSONKeys))
	for _, key := range ten_ai_base.DefaultJSONKeys {
		jsonKeySet[key] = struct{}{}
	}

	headerKeySet := make(map[string]struct{}, len(ten_ai_base.DefaultHeaderKeys))
	for _, key := range ten_ai_base.DefaultHeaderKeys {
		headerKeySet[key] = struct{}{}
	}

	if _, ok := headerKeySet["authorization"]; !ok {
		t.Fatal("authorization should be in DefaultHeaderKeys")
	}
	if _, ok := headerKeySet["x-api-key"]; !ok {
		t.Fatal("x-api-key should be in DefaultHeaderKeys")
	}
	if _, ok := jsonKeySet["secretkey"]; !ok {
		t.Fatal("secretkey should be in DefaultJSONKeys")
	}
	if _, ok := jsonKeySet["password"]; !ok {
		t.Fatal("password should be in DefaultJSONKeys")
	}
	if _, ok := jsonKeySet["x-api-key"]; !ok {
		t.Fatal("x-api-key should be in DefaultJSONKeys")
	}

	urlKeySet := make(map[string]struct{}, len(ten_ai_base.DefaultURLKeys))
	for _, key := range ten_ai_base.DefaultURLKeys {
		urlKeySet[key] = struct{}{}
	}
	if _, ok := urlKeySet["signature"]; !ok {
		t.Fatal("signature should be in DefaultURLKeys")
	}
	if _, ok := urlKeySet["secretid"]; !ok {
		t.Fatal("secretid should be in DefaultURLKeys")
	}
	if _, ok := urlKeySet["password"]; !ok {
		t.Fatal("password should be in DefaultURLKeys")
	}

	for _, headerKey := range ten_ai_base.DefaultHeaderKeys {
		if _, ok := jsonKeySet[headerKey]; !ok {
			t.Fatalf("DefaultJSONKeys missing header key %q", headerKey)
		}
	}
}

func TestRedactURL(t *testing.T) {
	rawURL := "wss://asr.cloud.tencent.com/asr/v2/1259678631?engine_model_type=16k_zh&secretid=AKIDabcdef123456&signature=abcdef%3D%3D&voice_id=visible#frag"

	got := ten_ai_base.RedactURL(rawURL)

	want := "wss://asr.cloud.tencent.com/asr/v2/1259678631?engine_model_type=16k_zh&secretid=" +
		ten_ai_base.MaskSecret("AKIDabcdef123456") +
		"&signature=" +
		ten_ai_base.MaskSecret("abcdef%3D%3D") +
		"&voice_id=visible#frag"
	if got != want {
		t.Fatalf("RedactURL() = %q, want %q", got, want)
	}
}

func TestRedactURLUsesDefaultKeysWhenOmitted(t *testing.T) {
	got := ten_ai_base.RedactURL("https://example.com/path?signature=abcdef123456&normal=visible")
	want := "https://example.com/path?signature=" + ten_ai_base.MaskSecret("abcdef123456") + "&normal=visible"
	if got != want {
		t.Fatalf("RedactURL() = %q, want %q", got, want)
	}
}

func TestRedactURLVariadicBoundaries(t *testing.T) {
	rawURL := "https://example.com/path?signature=default-123456&custom_flag=custom-123456&normal=visible"

	t.Run("omitted uses defaults", func(t *testing.T) {
		got := ten_ai_base.RedactURL(rawURL)
		want := "https://example.com/path?signature=" +
			ten_ai_base.MaskSecret("default-123456") +
			"&custom_flag=custom-123456&normal=visible"
		if got != want {
			t.Fatalf("RedactURL() = %q, want %q", got, want)
		}
	})

	t.Run("single custom slice", func(t *testing.T) {
		got := ten_ai_base.RedactURL(rawURL, []string{"custom_flag"})
		want := "https://example.com/path?signature=default-123456&custom_flag=" +
			ten_ai_base.MaskSecret("custom-123456") +
			"&normal=visible"
		if got != want {
			t.Fatalf("RedactURL() = %q, want %q", got, want)
		}
	})

	t.Run("empty slice disables redaction", func(t *testing.T) {
		if got := ten_ai_base.RedactURL(rawURL, []string{}); got != rawURL {
			t.Fatalf("RedactURL() = %q, want %q", got, rawURL)
		}
	})
}

func TestRedactURLKeepsURLWithoutQuery(t *testing.T) {
	rawURL := "wss://asr.cloud.tencent.com/asr/v2/1259678631"
	if got := ten_ai_base.RedactURL(rawURL); got != rawURL {
		t.Fatalf("RedactURL() = %q, want %q", got, rawURL)
	}
}

func TestEncryptCallsMaskSecret(t *testing.T) {
	value := "abcdef123456"
	if got, want := ten_ai_base.Encrypt(value), ten_ai_base.MaskSecret(value); got != want {
		t.Fatalf("Encrypt() = %q, want %q", got, want)
	}
}

func TestRedactHeaders(t *testing.T) {
	headers := map[string]string{
		"Authorization": "Bearer abcdef123456",
		"api-key":       "key-123456",
		"xi-api-key":    "xi-key-abcdef",
		"x-api-key":     "xkey-abcdef",
		"Content-Type":  "application/json",
	}

	got := ten_ai_base.RedactHeaders(headers, nil)

	if got["Authorization"] != ten_ai_base.MaskSecret("Bearer abcdef123456") {
		t.Fatalf("Authorization = %q", got["Authorization"])
	}
	if got["api-key"] != ten_ai_base.MaskSecret("key-123456") {
		t.Fatalf("api-key = %q", got["api-key"])
	}
	if got["xi-api-key"] != ten_ai_base.MaskSecret("xi-key-abcdef") {
		t.Fatalf("xi-api-key = %q", got["xi-api-key"])
	}
	if got["x-api-key"] != ten_ai_base.MaskSecret("xkey-abcdef") {
		t.Fatalf("x-api-key = %q", got["x-api-key"])
	}
	if got["Content-Type"] != "application/json" {
		t.Fatalf("Content-Type = %q", got["Content-Type"])
	}
	if ten_ai_base.RedactHeaders(nil, nil) != nil {
		t.Fatal("nil headers should stay nil")
	}
}

func TestRedactHeadersUsesDefaultKeysWhenOmitted(t *testing.T) {
	got := ten_ai_base.RedactHeaders(map[string]string{
		"Authorization": "Bearer abcdef123456",
		"Content-Type":  "application/json",
	})
	if got["Authorization"] != ten_ai_base.MaskSecret("Bearer abcdef123456") {
		t.Fatalf("Authorization = %q", got["Authorization"])
	}
	if got["Content-Type"] != "application/json" {
		t.Fatalf("Content-Type = %q", got["Content-Type"])
	}
}

func TestRedactHeadersVariadicBoundaries(t *testing.T) {
	headers := map[string]string{
		"Authorization":   "Bearer abcdef123456",
		"x-custom-secret": "custom-123456",
		"x-ignored":       "ignored-123456",
	}

	t.Run("omitted uses defaults", func(t *testing.T) {
		got := ten_ai_base.RedactHeaders(headers)
		if got["Authorization"] != ten_ai_base.MaskSecret("Bearer abcdef123456") {
			t.Fatalf("Authorization = %q", got["Authorization"])
		}
		if got["x-custom-secret"] != "custom-123456" {
			t.Fatalf("x-custom-secret = %q", got["x-custom-secret"])
		}
	})

	t.Run("single custom slice", func(t *testing.T) {
		got := ten_ai_base.RedactHeaders(headers, []string{"x-custom-secret"})
		if got["Authorization"] != "Bearer abcdef123456" {
			t.Fatalf("Authorization = %q", got["Authorization"])
		}
		if got["x-custom-secret"] != ten_ai_base.MaskSecret("custom-123456") {
			t.Fatalf("x-custom-secret = %q", got["x-custom-secret"])
		}
	})

	t.Run("single slice with multiple keys", func(t *testing.T) {
		got := ten_ai_base.RedactHeaders(
			headers,
			[]string{"x-custom-secret", "x-ignored"},
		)
		if got["x-custom-secret"] != ten_ai_base.MaskSecret("custom-123456") {
			t.Fatalf("x-custom-secret = %q", got["x-custom-secret"])
		}
		if got["x-ignored"] != ten_ai_base.MaskSecret("ignored-123456") {
			t.Fatalf("x-ignored = %q", got["x-ignored"])
		}
	})
}

func TestRedactHeadersCoversAllDefaultHeaderKeys(t *testing.T) {
	for _, headerKey := range ten_ai_base.DefaultHeaderKeys {
		t.Run(headerKey, func(t *testing.T) {
			got := ten_ai_base.RedactHeaders(map[string]string{
				headerKey:      "abcdef123456",
				"Content-Type": "application/json",
			})
			if got[headerKey] != ten_ai_base.MaskSecret("abcdef123456") {
				t.Fatalf("%s = %q", headerKey, got[headerKey])
			}
			if got["Content-Type"] != "application/json" {
				t.Fatalf("Content-Type = %q", got["Content-Type"])
			}
		})
	}
}

func TestRedactJSON(t *testing.T) {
	payload := map[string]any{
		"api_key": "abcdef123456",
		"nested": map[string]any{
			"Authorization": "Bearer super-secret-token",
			"normal":        "visible",
			"list": []any{
				map[string]any{"secret_key": "nested-secret"},
				map[string]any{"name": "kept"},
			},
		},
		"count":       3,
		"empty_token": "",
		"none_token":  nil,
	}

	redacted, err := ten_ai_base.RedactJSON(payload, nil)
	if err != nil {
		t.Fatalf("RedactJSON() error = %v", err)
	}
	got := redacted.(map[string]any)

	if got["api_key"] != ten_ai_base.MaskSecret("abcdef123456") {
		t.Fatalf("api_key = %#v", got["api_key"])
	}

	nested, ok := got["nested"].(map[string]any)
	if !ok {
		t.Fatalf("nested = %#v", got["nested"])
	}
	if nested["Authorization"] != ten_ai_base.MaskSecret("Bearer super-secret-token") {
		t.Fatalf("Authorization = %#v", nested["Authorization"])
	}
	if nested["normal"] != "visible" {
		t.Fatalf("normal = %#v", nested["normal"])
	}

	list, ok := nested["list"].([]any)
	if !ok || len(list) != 2 {
		t.Fatalf("list = %#v", nested["list"])
	}

	first, ok := list[0].(map[string]any)
	if !ok {
		t.Fatalf("list[0] = %#v", list[0])
	}
	if first["secret_key"] != ten_ai_base.MaskSecret("nested-secret") {
		t.Fatalf("secret_key = %#v", first["secret_key"])
	}

	second, ok := list[1].(map[string]any)
	if !ok {
		t.Fatalf("list[1] = %#v", list[1])
	}
	if second["name"] != "kept" {
		t.Fatalf("name = %#v", second["name"])
	}

	if got["count"] != float64(3) {
		t.Fatalf("count = %#v", got["count"])
	}
	if got["empty_token"] != "" {
		t.Fatalf("empty_token = %#v", got["empty_token"])
	}
	if got["none_token"] != nil {
		t.Fatalf("none_token = %#v", got["none_token"])
	}
}

func TestRedactJSONUsesDefaultKeysWhenOmitted(t *testing.T) {
	redacted, err := ten_ai_base.RedactJSON(map[string]any{"api_key": "abcdef123456"})
	if err != nil {
		t.Fatalf("RedactJSON() error = %v", err)
	}
	got := redacted.(map[string]any)
	if got["api_key"] != ten_ai_base.MaskSecret("abcdef123456") {
		t.Fatalf("api_key = %#v", got["api_key"])
	}
}

func TestRedactJSONVariadicBoundaries(t *testing.T) {
	payload := map[string]any{
		"api_key":     "default-123456",
		"custom_flag": "custom-123456",
		"extra_flag":  "extra-123456",
		"normal":      "visible",
	}

	t.Run("omitted uses defaults", func(t *testing.T) {
		redacted, err := ten_ai_base.RedactJSON(payload)
		if err != nil {
			t.Fatalf("RedactJSON() error = %v", err)
		}
		got := redacted.(map[string]any)
		if got["api_key"] != ten_ai_base.MaskSecret("default-123456") {
			t.Fatalf("api_key = %#v", got["api_key"])
		}
		if got["custom_flag"] != "custom-123456" {
			t.Fatalf("custom_flag = %#v", got["custom_flag"])
		}
	})

	t.Run("single custom slice", func(t *testing.T) {
		redacted, err := ten_ai_base.RedactJSON(payload, []string{"custom_flag"})
		if err != nil {
			t.Fatalf("RedactJSON() error = %v", err)
		}
		got := redacted.(map[string]any)
		if got["api_key"] != "default-123456" {
			t.Fatalf("api_key = %#v", got["api_key"])
		}
		if got["custom_flag"] != ten_ai_base.MaskSecret("custom-123456") {
			t.Fatalf("custom_flag = %#v", got["custom_flag"])
		}
		if got["extra_flag"] != "extra-123456" {
			t.Fatalf("extra_flag = %#v", got["extra_flag"])
		}
	})

	t.Run("single slice with multiple keys", func(t *testing.T) {
		redacted, err := ten_ai_base.RedactJSON(
			payload,
			[]string{"custom_flag", "extra_flag"},
		)
		if err != nil {
			t.Fatalf("RedactJSON() error = %v", err)
		}
		got := redacted.(map[string]any)
		if got["custom_flag"] != ten_ai_base.MaskSecret("custom-123456") {
			t.Fatalf("custom_flag = %#v", got["custom_flag"])
		}
		if got["extra_flag"] != ten_ai_base.MaskSecret("extra-123456") {
			t.Fatalf("extra_flag = %#v", got["extra_flag"])
		}
	})
}

func TestRedactJSONCoversAllDefaultJSONKeys(t *testing.T) {
	for _, jsonKey := range ten_ai_base.DefaultJSONKeys {
		t.Run(jsonKey, func(t *testing.T) {
			redacted, err := ten_ai_base.RedactJSON(map[string]any{
				jsonKey:  "abcdef123456",
				"normal": "visible",
			})
			if err != nil {
				t.Fatalf("RedactJSON() error = %v", err)
			}
			got := redacted.(map[string]any)
			if got[jsonKey] != ten_ai_base.MaskSecret("abcdef123456") {
				t.Fatalf("%s = %#v", jsonKey, got[jsonKey])
			}
			if got["normal"] != "visible" {
				t.Fatalf("normal = %#v", got["normal"])
			}
		})
	}
}

func TestRedactJSONMasksCompositeSensitiveValues(t *testing.T) {
	redacted, err := ten_ai_base.RedactJSON(map[string]any{
		"token":   map[string]any{"value": "secret-a"},
		"api_key": []any{"secret-a", "secret-b"},
	})
	if err != nil {
		t.Fatalf("RedactJSON() error = %v", err)
	}
	got := redacted.(map[string]any)
	if got["token"] != ten_ai_base.MaskSecret(`{"value":"secret-a"}`) {
		t.Fatalf("token = %#v", got["token"])
	}
	if got["api_key"] != ten_ai_base.MaskSecret(`["secret-a","secret-b"]`) {
		t.Fatalf("api_key = %#v", got["api_key"])
	}
}

func TestRedactJSONMatchesExactKeysOnly(t *testing.T) {
	redacted, err := ten_ai_base.RedactJSON(map[string]any{
		"monkey":          "banana",
		"keyboard_layout": "us",
		"token_bucket":    "bucket-secret",
		"token":           "real-secret",
	})
	if err != nil {
		t.Fatalf("RedactJSON() error = %v", err)
	}
	got := redacted.(map[string]any)
	if got["monkey"] != "banana" {
		t.Fatalf("monkey = %#v", got["monkey"])
	}
	if got["keyboard_layout"] != "us" {
		t.Fatalf("keyboard_layout = %#v", got["keyboard_layout"])
	}
	if got["token_bucket"] != "bucket-secret" {
		t.Fatalf("token_bucket = %#v", got["token_bucket"])
	}
	if got["token"] != ten_ai_base.MaskSecret("real-secret") {
		t.Fatalf("token = %#v", got["token"])
	}
}

func TestRedactJSONMarshalFailure(t *testing.T) {
	if _, err := ten_ai_base.RedactJSON(map[string]any{"bad": make(chan int)}, nil); err == nil {
		t.Fatal("RedactJSON() should fail on marshal error")
	}
}
