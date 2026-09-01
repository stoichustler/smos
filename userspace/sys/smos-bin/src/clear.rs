use std::ffi::OsString;
use std::io::{self, Write};

const CLEAR_SEQUENCE: &[u8] = b"\x1b[2J\x1b[H";

fn run<I, W>(args: I, output: &mut W) -> io::Result<i32>
where
    I: IntoIterator<Item = OsString>,
    W: Write,
{
    if args.into_iter().next().is_some() {
        return Ok(1);
    }
    output.write_all(CLEAR_SEQUENCE)?;
    output.flush()?;
    Ok(0)
}

fn main() {
    let stdout = io::stdout();
    let mut output = stdout.lock();
    let status = match run(std::env::args_os().skip(1), &mut output) {
        Ok(0) => 0,
        Ok(1) => {
            eprintln!("Usage: clear");
            1
        }
        Ok(status) => status,
        Err(error) => {
            eprintln!("clear: {error}");
            1
        }
    };
    std::process::exit(status);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::OsString;

    #[test]
    fn writes_ansi_clear_sequence() {
        let mut output = Vec::new();
        assert_eq!(run(Vec::<OsString>::new(), &mut output).unwrap(), 0);
        assert_eq!(output, b"\x1b[2J\x1b[H");
    }

    #[test]
    fn rejects_arguments() {
        let mut output = Vec::new();
        assert_eq!(run([OsString::from("unexpected")], &mut output).unwrap(), 1);
    }
}
