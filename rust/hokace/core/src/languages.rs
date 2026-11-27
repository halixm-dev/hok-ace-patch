//! `tools/languages.py`: the languages a patch installs, the catalog each reads and the terms its staged
//! text expands to. A catalog directory is its language, so everything language-specific is looked up
//! from its path.

use crate::terminology::{self, Term};
use std::path::{Path, PathBuf};

/// One language this patcher ships.
#[derive(Debug)]
pub struct Language {
    pub code: &'static str,
    pub name: &'static str,
    /// The catalog's directory name under the resources folder.
    pub catalog: &'static str,
    /// What `{Energy}`/`{LordExp}`/`{LordHp}` expand to, in the catalog's own word order.
    pub resource_terms: &'static [(&'static str, &'static str)],
}

impl Language {
    /// The glossary `terminology` applies to this language's catalog as it loads.
    pub fn terms(&self) -> &'static [Term] {
        if self.code == "id" {
            terminology::indonesian_terms()
        } else {
            terminology::english_terms_and_card_names()
        }
    }
}

/// `resource_tokens.RESOURCE_TOKENS`, the English terms.
pub const RESOURCE_TOKENS: &[(&str, &str)] = &[
    ("{Energy}", "Energy"),
    ("{LordExp}", "Chessplayer EXP"),
    ("{LordHp}", "Chessplayer HP"),
];

pub const ENGLISH: Language = Language {
    code: "en",
    name: "English",
    catalog: "catalog",
    resource_terms: RESOURCE_TOKENS,
};

/// The Indonesian catalog keeps the game's English terms but puts the head noun first.
pub const INDONESIAN: Language = Language {
    code: "id",
    name: "Bahasa Indonesia",
    catalog: "catalog_id",
    resource_terms: &[
        ("{Energy}", "Energy"),
        ("{LordExp}", "EXP Chessplayer"),
        ("{LordHp}", "HP Chessplayer"),
    ],
};

/// `LANGUAGES`, in its dict order.
pub const LANGUAGES: &[&Language] = &[&ENGLISH, &INDONESIAN];
pub const DEFAULT_LANGUAGE: &str = "en";

/// `languages.get`: the language for <code>, or the `ValueError` text for one this patcher lacks.
pub fn get(code: &str) -> Result<&'static Language, String> {
    LANGUAGES
        .iter()
        .copied()
        .find(|language| language.code == code)
        .ok_or_else(|| {
            let known: Vec<&str> = LANGUAGES.iter().map(|language| language.code).collect();
            format!(
                "unknown language {}; expected one of {}",
                crate::catalog::py_repr(code),
                known.join(", ")
            )
        })
}

/// `languages.catalog_dir`.
pub fn catalog_dir(resources: &Path, code: &str) -> Result<PathBuf, String> {
    Ok(resources.join(get(code)?.catalog))
}

/// `languages.for_catalog`: by the directory's name; an unrecognised name reads as English.
pub fn for_catalog(catalog: &Path) -> &'static Language {
    let name = catalog
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("");
    LANGUAGES
        .iter()
        .copied()
        .find(|language| language.catalog == name)
        .unwrap_or(&ENGLISH)
}

/// `languages.payload_path`: <catalog>'s own payload, or the English catalog's beside it.
pub fn payload_path(catalog: &Path, name: &str) -> PathBuf {
    let own = catalog.join(name);
    if own.exists() {
        return own;
    }
    let parent = catalog.parent().unwrap_or_else(|| Path::new(""));
    let fallback = parent.join(ENGLISH.catalog).join(name);
    if fallback.exists() { fallback } else { own }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn languages_by_code_and_folder() {
        assert_eq!(get("id").unwrap().catalog, "catalog_id");
        assert_eq!(
            get("fr").unwrap_err(),
            "unknown language 'fr'; expected one of en, id"
        );
        assert_eq!(for_catalog(Path::new("x/catalog_id")).code, "id");
        assert_eq!(for_catalog(Path::new("x/other")).code, "en");
    }
}
