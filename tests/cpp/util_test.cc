//
// This file is part of TEN Framework, an open source project.
// Licensed under the Apache License, Version 2.0.
// See the LICENSE file for more information.
//
#include "ten_ai_base/utils.h"

#include <gtest/gtest.h>

#include <map>
#include <string>
#include <vector>

namespace {

using ten_ai_base::Encrypt;
using ten_ai_base::MaskSecret;
using ten_ai_base::RedactHeaders;
using ten_ai_base::RedactJSON;
using ten_ai_base::RedactURL;

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

TEST(MaskSecretTest, EncryptAlias) {
  const std::string value = "abcdef123456";
  EXPECT_EQ(Encrypt(value), MaskSecret(value));
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

TEST(RedactHeadersTest, MasksKnownSensitiveHeaders) {
  const std::map<std::string, std::string> headers = {
      {"Authorization", "Bearer abcdef123456"},
      {"api-key", "key-123456"},
      {"Content-Type", "application/json"},
  };

  const auto sanitized = RedactHeaders(headers);
  EXPECT_EQ(sanitized.at("Authorization"), MaskSecret("Bearer abcdef123456"));
  EXPECT_EQ(sanitized.at("api-key"), MaskSecret("key-123456"));
  EXPECT_EQ(sanitized.at("Content-Type"), "application/json");
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
    "count": 3
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
