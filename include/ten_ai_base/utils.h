//
// This file is part of TEN Framework, an open source project.
// Licensed under the Apache License, Version 2.0.
// See the LICENSE file for more information.
//
#pragma once

#include <map>
#include <string>
#include <vector>

#include "nlohmann/json.hpp"

// Third-party integration (e.g. agora_rtm):
// 1. Add ten_ai_base to manifest.json dependencies.
// 2. Depend on the ten_ai_base target in BUILD.gn, or link utils.cc manually.
// 3. Add include dirs in BUILD.gn:
//      "//ten_packages/system/ten_ai_base/include"
//      "//.ten/app/ten_packages/system/ten_ai_base/include"
// 4. #include "ten_ai_base/utils.h"

namespace ten_ai_base {

const std::vector<std::string> &DefaultHeaderKeys();
const std::vector<std::string> &DefaultJSONKeys();
const std::vector<std::string> &DefaultURLKeys();

std::string MaskSecret(const std::string &value);
std::string Encrypt(const std::string &value);

std::map<std::string, std::string> RedactHeaders(
    const std::map<std::string, std::string> &headers,
    const std::vector<std::string> &header_keys);
std::map<std::string, std::string> RedactHeaders(
    const std::map<std::string, std::string> &headers);

std::string RedactURL(const std::string &raw_url,
                      const std::vector<std::string> &url_keys);
std::string RedactURL(const std::string &raw_url);

nlohmann::json RedactJSON(const nlohmann::json &value,
                          const std::vector<std::string> &json_keys);
nlohmann::json RedactJSON(const nlohmann::json &value);

std::string RedactJSONDump(const nlohmann::json &value,
                           const std::vector<std::string> &json_keys);
std::string RedactJSONDump(const nlohmann::json &value);

}  // namespace ten_ai_base
