//
// This file is part of TEN Framework, an open source project.
// Licensed under the Apache License, Version 2.0.
// See the LICENSE file for more information.
//
#include "ten_ai_base/utils.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <unordered_set>
#include <vector>

namespace {

size_t UTF8CodePointCount(const std::string &value) {
  size_t count = 0;
  for (size_t i = 0; i < value.size();) {
    const unsigned char ch = static_cast<unsigned char>(value[i]);
    if (ch < 0x80) {
      i += 1;
    } else if ((ch & 0xE0) == 0xC0) {
      i += 2;
    } else if ((ch & 0xF0) == 0xE0) {
      i += 3;
    } else if ((ch & 0xF8) == 0xF0) {
      i += 4;
    } else {
      i += 1;
    }
    ++count;
  }
  return count;
}

size_t UTF8ByteOffsetForCodePoint(const std::string &value,
                                  size_t code_point_index) {
  size_t current = 0;
  for (size_t i = 0; i < value.size();) {
    if (current == code_point_index) {
      return i;
    }
    const unsigned char ch = static_cast<unsigned char>(value[i]);
    if (ch < 0x80) {
      i += 1;
    } else if ((ch & 0xE0) == 0xC0) {
      i += 2;
    } else if ((ch & 0xF0) == 0xE0) {
      i += 3;
    } else if ((ch & 0xF8) == 0xF0) {
      i += 4;
    } else {
      i += 1;
    }
    ++current;
  }
  return value.size();
}

std::string SHA256FingerprintPrefix(const std::string &value) {
  static const uint32_t k[64] = {
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
      0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
      0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
      0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
      0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
      0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
      0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
      0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
      0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

  auto rotr = [](uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32U - n));
  };

  uint32_t h0 = 0x6a09e667;
  uint32_t h1 = 0xbb67ae85;
  uint32_t h2 = 0x3c6ef372;
  uint32_t h3 = 0xa54ff53a;
  uint32_t h4 = 0x510e527f;
  uint32_t h5 = 0x9b05688c;
  uint32_t h6 = 0x1f83d9ab;
  uint32_t h7 = 0x5be0cd19;

  std::vector<uint8_t> message(value.begin(), value.end());
  const uint64_t bit_len = message.size() * 8;
  message.push_back(0x80);
  while ((message.size() % 64) != 56) {
    message.push_back(0x00);
  }
  for (int i = 7; i >= 0; --i) {
    message.push_back(static_cast<uint8_t>((bit_len >> (i * 8)) & 0xFF));
  }

  for (size_t chunk = 0; chunk < message.size(); chunk += 64) {
    std::array<uint32_t, 64> w{};
    for (size_t i = 0; i < 16; ++i) {
      w[i] = (static_cast<uint32_t>(message[chunk + i * 4]) << 24) |
             (static_cast<uint32_t>(message[chunk + i * 4 + 1]) << 16) |
             (static_cast<uint32_t>(message[chunk + i * 4 + 2]) << 8) |
             static_cast<uint32_t>(message[chunk + i * 4 + 3]);
    }
    for (size_t i = 16; i < 64; ++i) {
      const uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^
                          (w[i - 15] >> 3);
      const uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^
                          (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }

    uint32_t a = h0;
    uint32_t b = h1;
    uint32_t c = h2;
    uint32_t d = h3;
    uint32_t e = h4;
    uint32_t f = h5;
    uint32_t g = h6;
    uint32_t h = h7;

    for (size_t i = 0; i < 64; ++i) {
      const uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const uint32_t ch = (e & f) ^ ((~e) & g);
      const uint32_t temp1 = h + s1 + ch + k[i] + w[i];
      const uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
      const uint32_t temp2 = s0 + maj;

      h = g;
      g = f;
      f = e;
      e = d + temp1;
      d = c;
      c = b;
      b = a;
      a = temp1 + temp2;
    }

    h0 += a;
    h1 += b;
    h2 += c;
    h3 += d;
    h4 += e;
    h5 += f;
    h6 += g;
    h7 += h;
  }

  const std::array<uint32_t, 8> hash = {h0, h1, h2, h3, h4, h5, h6, h7};
  std::ostringstream oss;
  oss << std::hex << std::setfill('0');
  for (size_t i = 0; i < 4; ++i) {
    oss << std::setw(2)
        << static_cast<unsigned>((hash[0] >> ((3 - i) * 8)) & 0xFF);
  }
  return oss.str();
}

std::string NormalizeKey(const std::string &key) {
  std::string normalized;
  normalized.reserve(key.size());
  for (unsigned char ch : key) {
    if (ch >= 'a' && ch <= 'z') {
      normalized.push_back(static_cast<char>(ch));
    } else if (ch >= 'A' && ch <= 'Z') {
      normalized.push_back(static_cast<char>(ch - 'A' + 'a'));
    } else if (ch >= '0' && ch <= '9') {
      normalized.push_back(static_cast<char>(ch));
    }
  }
  return normalized;
}

std::unordered_set<std::string> NormalizedKeySet(
    const std::vector<std::string> &keys) {
  std::unordered_set<std::string> normalized;
  normalized.reserve(keys.size());
  for (const auto &key : keys) {
    normalized.insert(NormalizeKey(key));
  }
  return normalized;
}

bool IsSensitiveKey(const std::string &key,
                    const std::unordered_set<std::string> &keys) {
  return keys.find(NormalizeKey(key)) != keys.end();
}

int HexValue(char ch) {
  if (ch >= '0' && ch <= '9') {
    return ch - '0';
  }
  if (ch >= 'a' && ch <= 'f') {
    return ch - 'a' + 10;
  }
  if (ch >= 'A' && ch <= 'F') {
    return ch - 'A' + 10;
  }
  return -1;
}

std::string QueryUnescape(const std::string &input) {
  std::string output;
  output.reserve(input.size());
  for (size_t i = 0; i < input.size(); ++i) {
    if (input[i] == '+') {
      output.push_back(' ');
    } else if (input[i] == '%' && i + 2 < input.size()) {
      const int hi = HexValue(input[i + 1]);
      const int lo = HexValue(input[i + 2]);
      if (hi >= 0 && lo >= 0) {
        output.push_back(static_cast<char>((hi << 4) | lo));
        i += 2;
        continue;
      }
      output.push_back(input[i]);
    } else {
      output.push_back(input[i]);
    }
  }
  return output;
}

nlohmann::json RedactValue(const nlohmann::json &value) {
  if (value.is_null()) {
    return value;
  }
  if (value.is_string()) {
    return ten_ai_base::MaskSecret(value.get<std::string>());
  }
  if (value.is_array() || value.is_object()) {
    return ten_ai_base::MaskSecret(value.dump());
  }
  return ten_ai_base::MaskSecret(value.dump());
}

nlohmann::json RedactJSONValue(
    const nlohmann::json &value,
    const std::unordered_set<std::string> &normalized_keys) {
  if (value.is_object()) {
    nlohmann::json redacted = nlohmann::json::object();
    for (auto it = value.begin(); it != value.end(); ++it) {
      const std::string &key = it.key();
      const nlohmann::json &item = it.value();
      if (IsSensitiveKey(key, normalized_keys)) {
        redacted[key] = RedactValue(item);
      } else {
        redacted[key] = RedactJSONValue(item, normalized_keys);
      }
    }
    return redacted;
  }
  if (value.is_array()) {
    nlohmann::json redacted = nlohmann::json::array();
    for (const auto &item : value) {
      redacted.push_back(RedactJSONValue(item, normalized_keys));
    }
    return redacted;
  }
  return value;
}

}  // namespace

namespace ten_ai_base {

const std::vector<std::string> &DefaultHeaderKeys() {
  static const std::vector<std::string> keys = {
      "authorization", "api-key", "x-api-key", "xi-api-key",
  };
  return keys;
}

const std::vector<std::string> &DefaultJSONKeys() {
  static const std::vector<std::string> keys = {
      "accesskey",  "apikey",       "appkey",       "authorization",
      "key",        "password",     "secret",       "secretid",
      "secretkey",  "ststoken",     "token",        "vendorkey",
      "vendorsecret",
      "api-key",    "x-api-key",    "xi-api-key",
  };
  return keys;
}

const std::vector<std::string> &DefaultURLKeys() {
  static const std::vector<std::string> keys = [] {
    std::vector<std::string> merged = {"sign", "signature"};
    const auto &json_keys = DefaultJSONKeys();
    merged.insert(merged.end(), json_keys.begin(), json_keys.end());
    return merged;
  }();
  return keys;
}

std::string MaskSecret(const std::string &value) {
  if (value.empty()) {
    return value;
  }

  const size_t code_points = UTF8CodePointCount(value);
  size_t step = code_points / 5;
  if (step == 0) {
    return value;
  }
  if (step > 5) {
    step = 5;
  }

  const size_t prefix_end = UTF8ByteOffsetForCodePoint(value, step);
  const size_t suffix_start =
      UTF8ByteOffsetForCodePoint(value, code_points - step);
  return value.substr(0, prefix_end) + "..." + value.substr(suffix_start) +
         "#" + SHA256FingerprintPrefix(value);
}

std::string Encrypt(const std::string &value) { return MaskSecret(value); }

std::map<std::string, std::string> RedactHeaders(
    const std::map<std::string, std::string> &headers,
    const std::vector<std::string> &header_keys) {
  if (headers.empty()) {
    return {};
  }

  std::unordered_set<std::string> lowered_keys;
  lowered_keys.reserve(header_keys.size());
  for (const auto &key : header_keys) {
    std::string lowered = key;
    std::transform(lowered.begin(), lowered.end(), lowered.begin(),
                   [](unsigned char ch) {
                     return static_cast<char>(std::tolower(ch));
                   });
    lowered_keys.insert(lowered);
  }

  std::map<std::string, std::string> redacted;
  for (auto it = headers.begin(); it != headers.end(); ++it) {
    const std::string &key = it->first;
    const std::string &value = it->second;
    std::string lowered = key;
    std::transform(lowered.begin(), lowered.end(), lowered.begin(),
                   [](unsigned char ch) {
                     return static_cast<char>(std::tolower(ch));
                   });
    if (lowered_keys.find(lowered) != lowered_keys.end()) {
      redacted[key] = MaskSecret(value);
    } else {
      redacted[key] = value;
    }
  }
  return redacted;
}

std::map<std::string, std::string> RedactHeaders(
    const std::map<std::string, std::string> &headers) {
  return RedactHeaders(headers, DefaultHeaderKeys());
}

std::string RedactURL(const std::string &raw_url,
                      const std::vector<std::string> &url_keys) {
  if (raw_url.empty()) {
    return raw_url;
  }

  const size_t query_start = raw_url.find('?');
  if (query_start == std::string::npos) {
    return raw_url;
  }

  const auto normalized_keys = NormalizedKeySet(url_keys);

  const std::string prefix = raw_url.substr(0, query_start + 1);
  std::string query_and_fragment = raw_url.substr(query_start + 1);
  std::string fragment;
  const size_t fragment_start = query_and_fragment.find('#');
  if (fragment_start != std::string::npos) {
    fragment = query_and_fragment.substr(fragment_start);
    query_and_fragment = query_and_fragment.substr(0, fragment_start);
  }
  if (query_and_fragment.empty()) {
    return raw_url;
  }

  std::vector<std::string> pairs;
  size_t start = 0;
  while (start <= query_and_fragment.size()) {
    const size_t amp = query_and_fragment.find('&', start);
    if (amp == std::string::npos) {
      pairs.push_back(query_and_fragment.substr(start));
      break;
    }
    pairs.push_back(query_and_fragment.substr(start, amp - start));
    start = amp + 1;
  }

  for (auto &pair : pairs) {
    if (pair.empty()) {
      continue;
    }
    const size_t equal_pos = pair.find('=');
    const std::string key =
        equal_pos == std::string::npos ? pair : pair.substr(0, equal_pos);
    if (!IsSensitiveKey(QueryUnescape(key), normalized_keys)) {
      continue;
    }
    if (equal_pos != std::string::npos) {
      const std::string value = pair.substr(equal_pos + 1);
      pair = key + "=" + MaskSecret(value);
    }
  }

  std::ostringstream oss;
  oss << prefix;
  for (size_t i = 0; i < pairs.size(); ++i) {
    if (i > 0) {
      oss << '&';
    }
    oss << pairs[i];
  }
  oss << fragment;
  return oss.str();
}

std::string RedactURL(const std::string &raw_url) {
  return RedactURL(raw_url, DefaultURLKeys());
}

nlohmann::json RedactJSON(const nlohmann::json &value,
                          const std::vector<std::string> &json_keys) {
  return RedactJSONValue(value, NormalizedKeySet(json_keys));
}

nlohmann::json RedactJSON(const nlohmann::json &value) {
  return RedactJSON(value, DefaultJSONKeys());
}

std::string RedactJSONDump(const nlohmann::json &value,
                           const std::vector<std::string> &json_keys) {
  return RedactJSON(value, json_keys).dump();
}

std::string RedactJSONDump(const nlohmann::json &value) {
  return RedactJSON(value).dump();
}

}  // namespace ten_ai_base
