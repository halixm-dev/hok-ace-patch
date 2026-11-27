//! Wire formats read by the localization runtime.

use std::fmt;

#[derive(Debug, PartialEq, Eq)]
pub enum Error {
    InvalidVarint,
    NegativeVarint,
    OffsetOutOfRange,
    FieldZero,
    TruncatedLength,
    TruncatedFixed32,
    TruncatedFixed64,
    UnsupportedWire(u8),
    AmbiguousLocalization,
    TruncatedLocalization,
    UnexpectedTable,
    UnexpectedRecordFields,
    MissingRecordFields,
    EmptyTable,
    Utf8 {
        start: usize,
        length: usize,
        byte: u8,
        reason: &'static str,
    },
}

impl Error {
    pub fn python_class(&self) -> &'static str {
        match self {
            Self::NegativeVarint => "ValueError",
            Self::OffsetOutOfRange => "IndexError",
            Self::Utf8 { .. } => "UnicodeDecodeError",
            _ => "ProtobufError",
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::InvalidVarint => "Invalid or truncated varint",
            Self::NegativeVarint => "Only unsigned varints are supported",
            Self::OffsetOutOfRange => "index out of range",
            Self::FieldZero => "Field zero is invalid",
            Self::TruncatedLength => "Truncated length-delimited field",
            Self::TruncatedFixed32 => "Truncated fixed32",
            Self::TruncatedFixed64 => "Truncated fixed64",
            Self::UnsupportedWire(wire) => return write!(f, "Unsupported wire type {wire}"),
            Self::AmbiguousLocalization => "Not an unambiguous localization table",
            Self::TruncatedLocalization => "Truncated localization field",
            Self::UnexpectedTable => "Top-level message is not a repeated I18N.Record table",
            Self::UnexpectedRecordFields => "I18N.Record contains unexpected fields",
            Self::MissingRecordFields => "I18N.Record is missing Key or Translation",
            Self::EmptyTable => "I18N table has no records",
            Self::Utf8 {
                start,
                length: 1,
                byte,
                reason,
            } => {
                return write!(
                    f,
                    "'utf-8' codec can't decode byte 0x{byte:02x} in position {start}: {reason}"
                );
            }
            Self::Utf8 {
                start,
                length,
                reason,
                ..
            } => {
                let end = start + length - 1;
                return write!(
                    f,
                    "'utf-8' codec can't decode bytes in position {start}-{end}: {reason}"
                );
            }
        })
    }
}

impl std::error::Error for Error {}

/// Reads up to ten varint bytes, preserving all 70 payload bits.
pub fn decode_varint(data: &[u8], offset: usize) -> Result<(u128, usize), Error> {
    let (value, end) = decode_varint_at(data, offset as i128)?;
    Ok((value, end as usize))
}

/// Negative offsets use the reference runtime's byte indexing.
pub fn decode_varint_at(data: &[u8], mut offset: i128) -> Result<(u128, i128), Error> {
    let mut value = 0;
    let len = data.len() as i128;
    for shift in (0..70).step_by(7) {
        if offset >= len {
            break;
        }
        let index = if offset < 0 { len + offset } else { offset };
        if index < 0 {
            return Err(Error::OffsetOutOfRange);
        }
        let byte = data[index as usize];
        offset += 1;
        value |= u128::from(byte & 127) << shift;
        if byte < 128 {
            return Ok((value, offset));
        }
    }
    Err(Error::InvalidVarint)
}

pub fn encode_varint(value: u128) -> Vec<u8> {
    let mut output = Vec::new();
    put_varint(&mut output, value);
    output
}

fn put_varint(output: &mut Vec<u8>, mut value: u128) {
    while value >= 128 {
        output.push((value as u8 & 127) | 128);
        value >>= 7;
    }
    output.push(value as u8);
}

fn take<'a>(
    data: &'a [u8],
    offset: &mut usize,
    size: u128,
    error: Error,
) -> Result<&'a [u8], Error> {
    let remaining = &data[*offset..];
    if size > remaining.len() as u128 {
        return Err(error);
    }
    let size = size as usize;
    *offset += size;
    Ok(&remaining[..size])
}

#[derive(Debug, PartialEq, Eq)]
pub enum Value<'a> {
    Varint(u128),
    Bytes(&'a [u8]),
}

#[derive(Debug, PartialEq, Eq)]
pub struct Field<'a> {
    pub number: u128,
    pub wire: u8,
    pub value: Value<'a>,
}

/// The general wire reader used by protobuf_i18n.
pub fn fields(data: &[u8]) -> impl Iterator<Item = Result<Field<'_>, Error>> {
    walk(data, |offset| {
        let (tag, end) = decode_varint(data, *offset)?;
        *offset = end;
        let number = tag >> 3;
        let wire = (tag & 7) as u8;
        if number == 0 {
            return Err(Error::FieldZero);
        }
        let value = match wire {
            0 => {
                let (value, end) = decode_varint(data, *offset)?;
                *offset = end;
                Value::Varint(value)
            }
            1 => Value::Bytes(take(data, offset, 8, Error::TruncatedFixed64)?),
            2 => {
                let (size, end) = decode_varint(data, *offset)?;
                *offset = end;
                Value::Bytes(take(data, offset, size, Error::TruncatedLength)?)
            }
            5 => Value::Bytes(take(data, offset, 4, Error::TruncatedFixed32)?),
            _ => return Err(Error::UnsupportedWire(wire)),
        };
        Ok(Field {
            number,
            wire,
            value,
        })
    })
}

#[derive(Debug, PartialEq, Eq)]
pub struct LocalizationField<'a> {
    pub tag: u8,
    pub payload: &'a [u8],
    pub raw: &'a [u8],
}

/// The stricter adaptive reader keeps the original framing for fields copied verbatim.
pub fn localization_fields(
    data: &[u8],
) -> impl Iterator<Item = Result<LocalizationField<'_>, Error>> {
    walk(data, |offset| {
        let start = *offset;
        let (tag, end) = decode_varint(data, start)?;
        if !matches!(tag, 10 | 18) {
            return Err(Error::AmbiguousLocalization);
        }
        let (size, end) = decode_varint(data, end)?;
        *offset = end;
        let payload = take(data, offset, size, Error::TruncatedLocalization)?;
        Ok(LocalizationField {
            tag: tag as u8,
            payload,
            raw: &data[start..*offset],
        })
    })
}

fn walk<T>(
    data: &[u8],
    mut read: impl FnMut(&mut usize) -> Result<T, Error>,
) -> impl Iterator<Item = Result<T, Error>> {
    let mut offset = 0;
    std::iter::from_fn(move || {
        if offset == data.len() {
            return None;
        }
        let result = read(&mut offset);
        if result.is_err() {
            offset = data.len();
        }
        Some(result)
    })
}

#[derive(Debug, PartialEq, Eq, Hash)]
pub struct Record<'a> {
    pub key: &'a str,
    pub translation: &'a str,
}

pub(crate) fn decode_str(data: &[u8]) -> Result<&str, Error> {
    std::str::from_utf8(data).map_err(|error| {
        let start = error.valid_up_to();
        let byte = data[start];
        let (length, reason) = match error.error_len() {
            None => (data.len() - start, "unexpected end of data"),
            Some(_) if !(0xc2..=0xf4).contains(&byte) => (1, "invalid start byte"),
            Some(length) => (length, "invalid continuation byte"),
        };
        Error::Utf8 {
            start,
            length,
            byte,
            reason,
        }
    })
}

pub fn parse_i18n(data: &[u8], strict: bool) -> Result<Vec<Record<'_>>, Error> {
    let top = fields(data).collect::<Result<Vec<_>, _>>()?;
    if strict && top.iter().any(|field| field.number != 1 || field.wire != 2) {
        return Err(Error::UnexpectedTable);
    }
    let mut records = Vec::new();
    for field in top {
        let Field {
            number: 1,
            wire: 2,
            value: Value::Bytes(payload),
        } = field
        else {
            continue;
        };
        let nested = fields(payload).collect::<Result<Vec<_>, _>>()?;
        if strict
            && nested
                .iter()
                .any(|field| !matches!(field.number, 1 | 2) || field.wire != 2)
        {
            return Err(Error::UnexpectedRecordFields);
        }
        let (mut key, mut translation) = (None, None);
        for field in nested {
            if let Field {
                wire: 2,
                number,
                value: Value::Bytes(value),
            } = field
            {
                match number {
                    1 => key = Some(decode_str(value)?),
                    2 => translation = Some(decode_str(value)?),
                    _ => {}
                }
            }
        }
        let (Some(key), Some(translation)) = (key, translation) else {
            return Err(Error::MissingRecordFields);
        };
        records.push(Record { key, translation });
    }
    if records.is_empty() {
        return Err(Error::EmptyTable);
    }
    Ok(records)
}

pub fn put_field(output: &mut Vec<u8>, tag: u8, bytes: &[u8]) {
    output.push(tag);
    put_varint(output, bytes.len() as u128);
    output.extend_from_slice(bytes);
}

pub fn serialize_i18n<'a>(records: impl IntoIterator<Item = Record<'a>>) -> Vec<u8> {
    let mut output = Vec::new();
    let mut nested = Vec::new();
    for record in records {
        nested.clear();
        put_field(&mut nested, 10, record.key.as_bytes());
        put_field(&mut nested, 18, record.translation.as_bytes());
        put_field(&mut output, 10, &nested);
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn varint_keeps_all_ten_payloads() {
        assert_eq!(
            decode_varint(&encode_varint((1 << 70) - 1), 0),
            Ok(((1 << 70) - 1, 10))
        );
        assert_eq!(
            decode_varint(&encode_varint(1 << 70), 0),
            Err(Error::InvalidVarint)
        );
        assert_eq!(decode_varint_at(&[3, 128], -1), Ok((384, 1)));
    }

    #[test]
    fn localization_keeps_noncanonical_headers() {
        let bytes = [0x8a, 0, 0x81, 0, b'a'];
        assert_eq!(
            localization_fields(&bytes).next(),
            Some(Ok(LocalizationField {
                tag: 10,
                payload: b"a",
                raw: &bytes,
            }))
        );
    }
}
