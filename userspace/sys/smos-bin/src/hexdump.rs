// Copyright 2026 The Fuchsia Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

use std::ffi::{OsStr, OsString};
use std::fs::File;
use std::io::{self, Read, Write};

fn usage() -> ! {
    eprintln!("Usage: hexdump [file ...]");
    std::process::exit(1);
}

fn format_line(offset: u64, bytes: &[u8]) -> String {
    let mut line = format!("{offset:08x}  ");
    for index in 0..16 {
        if let Some(byte) = bytes.get(index) {
            line.push_str(&format!("{byte:02x}"));
        } else {
            line.push_str("  ");
        }
        line.push(' ');
        if index == 7 {
            line.push(' ');
        }
    }
    line.push('|');
    for &byte in bytes {
        line.push(if (0x20..=0x7e).contains(&byte) { byte as char } else { '.' });
    }
    for _ in bytes.len()..16 {
        line.push(' ');
    }
    line.push('|');
    line.push('\n');
    line
}

fn dump<R: Read, W: Write>(reader: &mut R, writer: &mut W, mut offset: u64) -> io::Result<u64> {
    let mut buffer = [0u8; 16];
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            return Ok(offset);
        }
        writer.write_all(format_line(offset, &buffer[..count]).as_bytes())?;
        offset = offset.saturating_add(count as u64);
    }
}

fn run<I>(args: I) -> i32
where
    I: IntoIterator<Item = OsString>,
{
    let mut files = Vec::new();
    let mut options = true;
    for arg in args {
        if options && arg == OsStr::new("--") {
            options = false;
        } else if options && arg.to_string_lossy().starts_with('-') && arg != OsStr::new("-") {
            usage();
        } else {
            options = false;
            files.push(arg);
        }
    }

    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut input = stdin.lock();
    let mut output = stdout.lock();
    let mut status = 0;
    let mut offset = 0;

    if files.is_empty() {
        if let Err(error) = dump(&mut input, &mut output, offset) {
            eprintln!("hexdump: <stdin>: {error}");
            status = 1;
        }
    } else {
        for path in files {
            if path == OsStr::new("-") {
                match dump(&mut input, &mut output, offset) {
                    Ok(next_offset) => offset = next_offset,
                    Err(error) => {
                        eprintln!("hexdump: <stdin>: {error}");
                        status = 1;
                    }
                }
                continue;
            }

            match File::open(&path) {
                Ok(mut file) => match dump(&mut file, &mut output, offset) {
                    Ok(next_offset) => offset = next_offset,
                    Err(error) => {
                        eprintln!("hexdump: {}: {error}", path.to_string_lossy());
                        status = 1;
                    }
                },
                Err(error) => {
                    eprintln!("hexdump: {}: {error}", path.to_string_lossy());
                    status = 1;
                }
            }
        }
    }

    if let Err(error) = output.flush() {
        eprintln!("hexdump: <stdout>: {error}");
        status = 1;
    }
    status
}

fn main() {
    std::process::exit(run(std::env::args_os().skip(1)));
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn formats_full_line() {
        let bytes: Vec<u8> = (0..16).collect();
        assert_eq!(
            format_line(0, &bytes),
            "00000000  00 01 02 03 04 05 06 07  08 09 0a 0b 0c 0d 0e 0f |................|\n"
        );
    }

    #[test]
    fn formats_short_line_and_ascii() {
        assert_eq!(
            format_line(16, b"A\n\xff"),
            "00000010  41 0a ff                                         |A..             |\n"
        );
    }

    #[test]
    fn dumps_multiple_chunks_with_offsets() {
        let mut input = Cursor::new((0..20).collect::<Vec<u8>>());
        let mut output = Vec::new();
        let offset = dump(&mut input, &mut output, 0).unwrap();
        assert_eq!(offset, 20);
        assert!(String::from_utf8(output).unwrap().starts_with("00000000  "));
    }
}
