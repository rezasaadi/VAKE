use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer};
use std::{collections::BTreeSet, fmt};

struct Unique;
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct Check;
        impl<'de> Visitor<'de> for Check {
            type Value = Unique;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("JSON without duplicate object keys")
            }
            fn visit_bool<E: de::Error>(self, _: bool) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_i64<E: de::Error>(self, _: i64) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_u64<E: de::Error>(self, _: u64) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_f64<E: de::Error>(self, _: f64) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_str<E: de::Error>(self, _: &str) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_unit<E: de::Error>(self) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut a: A) -> Result<Unique, A::Error> {
                while a.next_element::<Unique>()?.is_some() {}
                Ok(Unique)
            }
            fn visit_map<A: MapAccess<'de>>(self, mut a: A) -> Result<Unique, A::Error> {
                let mut seen = BTreeSet::new();
                while let Some(k) = a.next_key::<String>()? {
                    if !seen.insert(k.clone()) {
                        return Err(de::Error::custom(format!("duplicate JSON key: {k}")));
                    }
                    a.next_value::<Unique>()?;
                }
                Ok(Unique)
            }
        }
        d.deserialize_any(Check)
    }
}
pub fn unique(bytes: &[u8]) -> Result<(), String> {
    serde_json::from_slice::<Unique>(bytes)
        .map(|_| ())
        .map_err(|e| e.to_string())
}
