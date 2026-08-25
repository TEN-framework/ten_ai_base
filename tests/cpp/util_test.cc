//
// This file is part of TEN Framework, an open source project.
// Licensed under the Apache License, Version 2.0.
// See the LICENSE file for more information.
//
#include "ten_ai_base/utils.h"

#include <gtest/gtest.h>

#include <map>
#include <string>
#include <unordered_set>
#include <vector>

namespace {

using ten_ai_base::DefaultHeaderKeys;
using ten_ai_base::DefaultJSONKeys;
using ten_ai_base::DefaultURLKeys;
using ten_ai_base::Encrypt;
using ten_ai_base::MaskSecret;
using ten_ai_base::RedactHeaders;
using ten_ai_base::RedactJSON;
using ten_ai_base::RedactURL;

std::unordered_set<std::string> KeySet(const std::vector<std::string> &keys) {
  return std::unordered_set<std::string>(keys.begin(), keys.end());
}

}  // namespace

TEST(MaskSecretTest, MasksLongValues) {
  EXPECT_EQ(MaskSecret("1234567890"), "12...90#c775e7b7");
  EXPECT_EQ(MaskSecret("abcdefghijklmnopqrstuvwxyz"),
            "abcde...vwxyz#71c480df");
}

TEST(MaskSecretTest, KeepsShortValues) {
  EXPECT_EQ(MaskSecret(""), "");
  EXPECT_EQ(MaskSecret("a"), "a");
  EXPECT_EQ(MaskSecret("ab"), "ab");
  EXPECT_EQ(MaskSecret("张"), "张");
  EXPECT_EQ(MaskSecret("abcd"), "abcd");
}

TEST(MaskSecretTest, SupportsModes) {
  const std::map<std::string, std::string> cases = {
      {"13800138000", "13...00#a6942f97"},
      {"+8613800138000", "+8...00#ec61f3c6"},
      {"alice@example.com", "ali...com#ff8d9819"},
      {"a@example.com", "a@...om#08168cd8"},
      {"110101199001011234", "110...234#04e7358a"},
      {"192.168.10.23", "19...23#85512b03"},
  };

  for (const auto &item : cases) {
    SCOPED_TRACE(item.first);
    EXPECT_EQ(MaskSecret(item.first), item.second);
  }
}

TEST(MaskSecretTest, DefaultModeHasFingerprint) {
  const std::string got = MaskSecret("Bearer abcdef123456");
  EXPECT_EQ(got.rfind("Bea...456#", 0), 0U);

  const auto hash_pos = got.find('#');
  ASSERT_NE(hash_pos, std::string::npos);
  EXPECT_EQ(got.size() - hash_pos - 1, 8U);
}

TEST(MaskSecretTest, EncryptAlias) {
  const std::string value = "abcdef123456";
  EXPECT_EQ(Encrypt(value), MaskSecret(value));
}

TEST(DefaultKeysTest, IncludesExpectedItems) {
  const auto &header_keys = DefaultHeaderKeys();
  const auto &json_keys = DefaultJSONKeys();
  const auto &url_keys = DefaultURLKeys();

  ASSERT_FALSE(header_keys.empty());
  ASSERT_FALSE(json_keys.empty());
  ASSERT_FALSE(url_keys.empty());

  const auto header_set = KeySet(header_keys);
  const auto json_set = KeySet(json_keys);
  const auto url_set = KeySet(url_keys);

  EXPECT_TRUE(header_set.count("authorization"));
  EXPECT_TRUE(header_set.count("x-api-key"));
  EXPECT_TRUE(json_set.count("secretkey"));
  EXPECT_TRUE(json_set.count("password"));
  EXPECT_TRUE(json_set.count("x-api-key"));
  EXPECT_TRUE(url_set.count("signature"));
  EXPECT_TRUE(url_set.count("secretid"));
  EXPECT_TRUE(url_set.count("password"));

  for (const auto &header_key : header_keys) {
    EXPECT_TRUE(json_set.count(header_key))
        << "DefaultJSONKeys missing header key " << header_key;
  }
}

TEST(RedactURLTest, MasksSensitiveQueryValues) {
  const std::string raw_url =
      "wss://asr.cloud.tencent.com/asr/v2/1259678631"
      "?engine_model_type=16k_zh"
      "&secretid=AKIDabcdef123456"
      "&signature=abcdef%3D%3D"
      "&voice_id=visible#frag";

  const std::string want =
      "wss://asr.cloud.tencent.com/asr/v2/1259678631"
      "?engine_model_type=16k_zh"
      "&secretid=" +
      MaskSecret("AKIDabcdef123456") +
      "&signature=" + MaskSecret("abcdef%3D%3D") +
      "&voice_id=visible#frag";

  EXPECT_EQ(RedactURL(raw_url), want);
}

TEST(RedactURLTest, UsesDefaultKeysWhenOmitted) {
  const std::string got = RedactURL(
      "https://example.com/path?signature=abcdef123456&normal=visible");
  const std::string want =
      "https://example.com/path?signature=" +
      MaskSecret("abcdef123456") + "&normal=visible";
  EXPECT_EQ(got, want);
}

TEST(RedactURLTest, KeyBoundaries) {
  const std::string raw_url =
      "https://example.com/path"
      "?signature=default-123456&custom_flag=custom-123456&normal=visible";

  const std::string omitted =
      "https://example.com/path?signature=" +
      MaskSecret("default-123456") +
      "&custom_flag=custom-123456&normal=visible";
  EXPECT_EQ(RedactURL(raw_url), omitted);

  const std::string single =
      "https://example.com/path?signature=default-123456&custom_flag=" +
      MaskSecret("custom-123456") + "&normal=visible";
  EXPECT_EQ(RedactURL(raw_url, std::vector<std::string>{"custom_flag"}),
            single);

  EXPECT_EQ(RedactURL(raw_url, std::vector<std::string>{}), raw_url);
}

TEST(RedactURLTest, KeepsURLWithoutQuery) {
  const std::string raw_url = "wss://asr.cloud.tencent.com/asr/v2/1259678631";
  EXPECT_EQ(RedactURL(raw_url), raw_url);
}

TEST(RedactHeadersTest, MasksKnownSensitiveHeaders) {
  const std::map<std::string, std::string> headers = {
      {"Authorization", "Bearer abcdef123456"},
      {"api-key", "key-123456"},
      {"xi-api-key", "xi-key-abcdef"},
      {"x-api-key", "xkey-abcdef"},
      {"Content-Type", "application/json"},
  };

  const auto sanitized = RedactHeaders(headers);
  EXPECT_EQ(sanitized.at("Authorization"), MaskSecret("Bearer abcdef123456"));
  EXPECT_EQ(sanitized.at("api-key"), MaskSecret("key-123456"));
  EXPECT_EQ(sanitized.at("xi-api-key"), MaskSecret("xi-key-abcdef"));
  EXPECT_EQ(sanitized.at("x-api-key"), MaskSecret("xkey-abcdef"));
  EXPECT_EQ(sanitized.at("Content-Type"), "application/json");
}

TEST(RedactHeadersTest, KeepsEmptyInputShape) {
  EXPECT_TRUE(RedactHeaders({}).empty());
}

TEST(RedactHeadersTest, UsesDefaultKeysWhenOmitted) {
  const auto sanitized = RedactHeaders({
      {"Authorization", "Bearer abcdef123456"},
      {"Content-Type", "application/json"},
  });
  EXPECT_EQ(sanitized.at("Authorization"), MaskSecret("Bearer abcdef123456"));
  EXPECT_EQ(sanitized.at("Content-Type"), "application/json");
}

TEST(RedactHeadersTest, KeyBoundaries) {
  const std::map<std::string, std::string> headers = {
      {"Authorization", "Bearer abcdef123456"},
      {"x-custom-secret", "custom-123456"},
      {"x-extra-secret", "extra-123456"},
  };

  const auto omitted = RedactHeaders(headers);
  EXPECT_EQ(omitted.at("Authorization"), MaskSecret("Bearer abcdef123456"));
  EXPECT_EQ(omitted.at("x-custom-secret"), "custom-123456");

  const auto single = RedactHeaders(
      headers, std::vector<std::string>{"x-custom-secret"});
  EXPECT_EQ(single.at("Authorization"), "Bearer abcdef123456");
  EXPECT_EQ(single.at("x-custom-secret"), MaskSecret("custom-123456"));
  EXPECT_EQ(single.at("x-extra-secret"), "extra-123456");

  const auto multiple = RedactHeaders(
      headers,
      std::vector<std::string>{"x-custom-secret", "x-extra-secret"});
  EXPECT_EQ(multiple.at("Authorization"), "Bearer abcdef123456");
  EXPECT_EQ(multiple.at("x-custom-secret"), MaskSecret("custom-123456"));
  EXPECT_EQ(multiple.at("x-extra-secret"), MaskSecret("extra-123456"));
}

TEST(RedactHeadersTest, CoversAllDefaultHeaderKeys) {
  for (const auto &header_key : DefaultHeaderKeys()) {
    SCOPED_TRACE(header_key);
    const auto sanitized = RedactHeaders({
        {header_key, "abcdef123456"},
        {"Content-Type", "application/json"},
    });
    EXPECT_EQ(sanitized.at(header_key), MaskSecret("abcdef123456"));
    EXPECT_EQ(sanitized.at("Content-Type"), "application/json");
  }
}

TEST(RedactHeadersTest, EmptyKeySetKeepsValues) {
  const std::map<std::string, std::string> headers = {
      {"Authorization", "Bearer abcdef123456"},
      {"normal", "visible"},
  };
  const auto sanitized = RedactHeaders(headers, std::vector<std::string>{});
  EXPECT_EQ(sanitized.at("Authorization"), "Bearer abcdef123456");
  EXPECT_EQ(sanitized.at("normal"), "visible");
}

TEST(RedactJSONTest, RedactsSensitiveFieldsRecursively) {
  const nlohmann::json payload = nlohmann::json::parse(R"({
    "api_key": "abcdef123456",
    "nested": {
      "Authorization": "Bearer super-secret-token",
      "normal": "visible",
      "list": [
        {"secret_key": "nested-secret"},
        {"name": "kept"}
      ]
    },
    "count": 3,
    "empty_token": "",
    "none_token": null
  })");

  const auto redacted = RedactJSON(payload);
  EXPECT_EQ(redacted["api_key"], MaskSecret("abcdef123456"));
  EXPECT_EQ(redacted["nested"]["Authorization"],
            MaskSecret("Bearer super-secret-token"));
  EXPECT_EQ(redacted["nested"]["normal"], "visible");
  EXPECT_EQ(redacted["nested"]["list"][0]["secret_key"],
            MaskSecret("nested-secret"));
  EXPECT_EQ(redacted["nested"]["list"][1]["name"], "kept");
  EXPECT_EQ(redacted["count"], 3);
  EXPECT_EQ(redacted["empty_token"], "");
  EXPECT_TRUE(redacted["none_token"].is_null());
}

TEST(RedactJSONTest, UsesDefaultKeysWhenOmitted) {
  const nlohmann::json payload = {{"api_key", "abcdef123456"}};
  const auto redacted = RedactJSON(payload);
  EXPECT_EQ(redacted["api_key"], MaskSecret("abcdef123456"));
}

TEST(RedactJSONTest, KeyBoundaries) {
  const nlohmann::json payload = {
      {"api_key", "default-123456"},
      {"custom_flag", "custom-123456"},
      {"extra_flag", "extra-123456"},
      {"normal", "visible"},
  };

  const auto omitted = RedactJSON(payload);
  EXPECT_EQ(omitted["api_key"], MaskSecret("default-123456"));
  EXPECT_EQ(omitted["custom_flag"], "custom-123456");

  const auto single =
      RedactJSON(payload, std::vector<std::string>{"custom_flag"});
  EXPECT_EQ(single["api_key"], "default-123456");
  EXPECT_EQ(single["custom_flag"], MaskSecret("custom-123456"));
  EXPECT_EQ(single["extra_flag"], "extra-123456");

  const auto multiple = RedactJSON(
      payload, std::vector<std::string>{"custom_flag", "extra_flag"});
  EXPECT_EQ(multiple["api_key"], "default-123456");
  EXPECT_EQ(multiple["custom_flag"], MaskSecret("custom-123456"));
  EXPECT_EQ(multiple["extra_flag"], MaskSecret("extra-123456"));
}

TEST(RedactJSONTest, CoversAllDefaultJSONKeys) {
  for (const auto &json_key : DefaultJSONKeys()) {
    SCOPED_TRACE(json_key);
    const nlohmann::json payload = {
        {json_key, "abcdef123456"},
        {"normal", "visible"},
    };
    const auto redacted = RedactJSON(payload);
    EXPECT_EQ(redacted[json_key], MaskSecret("abcdef123456"));
    EXPECT_EQ(redacted["normal"], "visible");
  }
}

TEST(RedactJSONTest, MasksCompositeSensitiveValues) {
  const nlohmann::json payload = {
      {"token", nlohmann::json{{"value", "secret-a"}}},
      {"api_key", nlohmann::json::array({"secret-a", "secret-b"})},
  };

  const auto redacted = RedactJSON(payload);
  EXPECT_EQ(redacted["token"], MaskSecret(R"({"value":"secret-a"})"));
  EXPECT_EQ(redacted["api_key"], MaskSecret(R"(["secret-a","secret-b"])"));
}

TEST(RedactJSONTest, MatchesExactKeysOnly) {
  const nlohmann::json payload = {
      {"monkey", "banana"},
      {"keyboard_layout", "us"},
      {"token_bucket", "bucket-secret"},
      {"token", "real-secret"},
  };

  const auto redacted = RedactJSON(payload);
  EXPECT_EQ(redacted["monkey"], "banana");
  EXPECT_EQ(redacted["keyboard_layout"], "us");
  EXPECT_EQ(redacted["token_bucket"], "bucket-secret");
  EXPECT_EQ(redacted["token"], MaskSecret("real-secret"));
}

TEST(RedactJSONTest, SupportsCustomKeys) {
  const nlohmann::json payload = {
      {"custom_flag", "custom-123456"},
      {"api_key", "default-123456"},
  };

  const auto redacted =
      RedactJSON(payload, std::vector<std::string>{"custom_flag"});
  EXPECT_EQ(redacted["custom_flag"], MaskSecret("custom-123456"));
  EXPECT_EQ(redacted["api_key"], "default-123456");
}

TEST(RedactJSONTest, EmptyKeySetKeepsValues) {
  const nlohmann::json payload = {{"api_key", "abcdef123456"}};
  const auto redacted = RedactJSON(payload, std::vector<std::string>{});
  EXPECT_EQ(redacted["api_key"], "abcdef123456");
}
