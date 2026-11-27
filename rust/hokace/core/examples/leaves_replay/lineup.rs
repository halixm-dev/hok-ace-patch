//! The `config_bin`, `pb_text`, `lineup_codes` and `unity_text` calls of rust/harness/lineup_cases.py.

use hokace_core::axml::PyErr;
use hokace_core::config_bin::{self, Field};
use hokace_core::resource_tokens::NotMessage;
use hokace_core::{lineup_codes, pb_text, unity_text};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::Path;

fn hex(data: &[u8]) -> String {
    data.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn unhex(text: &str) -> Vec<u8> {
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap())
        .collect()
}

fn sha(data: &[u8]) -> String {
    hex(&Sha256::digest(data))
}

fn blob(data: &[u8]) -> Value {
    json!(if data.len() <= 2048 {
        hex(data)
    } else {
        format!("sha256:{}", sha(data))
    })
}

fn texts(offered: &[String]) -> Value {
    let joined = offered.join("\0");
    if joined.len() <= 2048 {
        json!(offered)
    } else {
        json!([offered.len(), sha(joined.as_bytes())])
    }
}

fn answer(mode: &str, text: &str) -> Option<String> {
    if mode == "all" {
        return Some(format!("EN:{text}"));
    }
    let n = text.chars().count();
    match n % 4 {
        0 => None,
        1 => Some(text.to_owned()),
        2 => Some(String::new()),
        _ => Some(format!("EN{n}:{}", text.chars().rev().collect::<String>())),
    }
}

fn value(value: &config_bin::Value) -> String {
    match value {
        config_bin::Value::Int(number) => format!("i:{number}"),
        config_bin::Value::Bytes(bytes) => format!("b:{}", hex(bytes)),
    }
}

fn entries_digest(entries: &[Field]) -> String {
    let text: String = entries
        .iter()
        .map(|field| format!("{},{},{};", field.number, field.wire, value(&field.value)))
        .collect();
    sha(text.as_bytes())
}

fn parse_entries(spec: &Value) -> Vec<Field> {
    spec.as_array()
        .unwrap()
        .iter()
        .map(|entry| {
            let text = entry[2].as_str().unwrap();
            Field {
                number: entry[0].as_str().unwrap().parse().unwrap(),
                wire: entry[1].as_u64().unwrap() as u8,
                value: match text.strip_prefix("i:") {
                    Some(number) => config_bin::Value::Int(number.parse().unwrap()),
                    None => config_bin::Value::Bytes(unhex(&text[2..])),
                },
            }
        })
        .collect()
}

fn py(result: Result<Value, PyErr>) -> Value {
    match result {
        Ok(value) => json!({"ok": value}),
        Err(error) => json!({"error": format!("{}: {}", error.class, error.message)}),
    }
}

fn not_message(result: Result<Value, NotMessage>) -> Value {
    py(result.map_err(|NotMessage| PyErr::new("NotMessage", "")))
}

fn hash_arg(args: &Value) -> u64 {
    u64::from_str_radix(args["hash"].as_str().unwrap(), 16).unwrap()
}

/// The result of one recorded call, or None when <function> is not one of these.
pub fn call(dir: &Path, function: &str, args: &Value) -> Option<Value> {
    let s = |key: &str| args[key].as_str().unwrap_or_default().to_owned();
    let file = || fs::read(dir.join(s("file"))).unwrap();
    let mode = s("mode");
    let mut offered: Vec<String> = Vec::new();
    let result = match function {
        "cb_fields" => {
            py(config_bin::fields(&file()).map(|entries| json!(entries_digest(&entries))))
        }
        "cb_encode" => py(config_bin::fields(&file())
            .and_then(|e| config_bin::encode(&e))
            .map(|out| blob(&out))),
        "cb_rows_md5" => py(config_bin::fields(&file())
            .and_then(|e| config_bin::rows_md5(&e))
            .map(|digest| json!(String::from_utf8(digest).unwrap()))),
        "cb_checksum" => py(config_bin::fields(&file())
            .and_then(|e| config_bin::checksum(&e))
            .map(|sum| json!(sum))),
        "cb_reseal" => py(config_bin::fields(&file())
            .and_then(|e| config_bin::reseal(&e))
            .and_then(|e| config_bin::encode(&e))
            .map(|out| blob(&out))),
        "cb_is_sealed" => py(config_bin::is_sealed(&file()).map(|sealed| json!(sealed))),
        "cb_entries" => {
            let entries = parse_entries(&args["entries"]);
            py(match s("op").as_str() {
                "encode" => config_bin::encode(&entries).map(|out| json!(hex(&out))),
                "rows_md5" => config_bin::rows_md5(&entries)
                    .map(|digest| json!(String::from_utf8(digest).unwrap())),
                "checksum" => config_bin::checksum(&entries).map(|sum| json!(sum)),
                _ => config_bin::reseal(&entries).map(|sealed| {
                    json!(
                        sealed
                            .iter()
                            .map(|field| json!([
                                field.number.to_string(),
                                field.wire,
                                value(&field.value)
                            ]))
                            .collect::<Vec<_>>()
                    )
                }),
            })
        }
        "pb_rewrite" => {
            let depth = args["depth"].as_u64().unwrap() as u32;
            let mut translate = |text: &str| {
                offered.push(text.to_owned());
                answer(&mode, text)
            };
            let result = pb_text::rewrite(&file(), &mut translate, depth);
            not_message(result.map(|(out, count)| json!([blob(&out), count, texts(&offered)])))
        }
        "pb_collect" => {
            let depth = args["depth"].as_u64().unwrap() as u32;
            not_message(pb_text::collect(&file(), depth).map(|found| texts(&found)))
        }
        "lc_decode" => py(lineup_codes::decode_code(&unhex(&s("code"))).map(|out| blob(&out))),
        "lc_encode" => json!({"ok": blob(&lineup_codes::encode_code(&file()))}),
        "lc_rewrite_code" => {
            let mut translate = |text: &str| {
                offered.push(text.to_owned());
                answer(&mode, text)
            };
            let result = lineup_codes::rewrite_code(&unhex(&s("code")), &mut translate);
            py(result.map(|(out, count)| json!([blob(&out), count, texts(&offered)])))
        }
        "lc_rewrite_bin" => {
            let mut translate = |text: &str| {
                offered.push(text.to_owned());
                answer(&mode, text)
            };
            let result = lineup_codes::rewrite_bin(hash_arg(args), &file(), &mut translate);
            py(result.map(|(out, count)| json!([blob(&out), count, texts(&offered)])))
        }
        "lc_strings" => {
            py(lineup_codes::strings(hash_arg(args), &file()).map(|found| texts(&found)))
        }
        "ut_parse" => {
            let data = file();
            py(unity_text::SerializedFile::parse(&data).map(|parsed| {
                let objects: Vec<Value> = parsed
                    .objects
                    .iter()
                    .map(|o| json!([o.table, o.path_id, o.start, o.size, o.type_index]))
                    .collect();
                json!([
                    parsed.metadata_size,
                    parsed.file_size,
                    parsed.data_offset,
                    parsed.class_ids,
                    objects
                ])
            }))
        }
        "ut_rewrite" => {
            let data = file();
            let mut translate = |text: &str| {
                offered.push(text.to_owned());
                answer(&mode, text)
            };
            let result = unity_text::SerializedFile::parse(&data)
                .and_then(|parsed| parsed.rewrite(&mut translate));
            py(result.map(|(out, count)| json!([blob(&out), count, texts(&offered)])))
        }
        "ut_strings" => {
            let mut translate = |text: &str| {
                offered.push(text.to_owned());
                answer(&mode, text)
            };
            let (out, count) = unity_text::rewrite_strings(&unhex(&s("body")), &mut translate);
            json!({"ok": [hex(&out), count, offered]})
        }
        _ => return None,
    };
    Some(result)
}
