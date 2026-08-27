use std::ffi::{OsStr, OsString};
use std::fs::File;
use std::io::{self, Read, Write};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Metric {
    Lines,
    Words,
    Bytes,
    Chars,
    LongestLine,
}

#[derive(Debug, PartialEq, Eq)]
struct Options {
    metrics: Vec<Metric>,
    paths: Vec<OsString>,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Counts {
    lines: usize,
    words: usize,
    bytes: usize,
    chars: usize,
    longest_line: usize,
}

fn usage() -> ! {
    eprintln!("Usage: wc [-lwmcL] [file ...]");
    std::process::exit(1);
}

fn parse_args<I>(args: I) -> Result<Options, String>
where
    I: IntoIterator<Item = OsString>,
{
    let args: Vec<OsString> = args.into_iter().collect();
    let mut metrics = Vec::new();
    let mut paths = Vec::new();
    let mut parse_options = true;
    let mut index = 0;
    while index < args.len() {
        let arg = &args[index];
        let text = arg.to_string_lossy();
        if parse_options && arg == OsStr::new("--") {
            parse_options = false;
        } else if parse_options && text.starts_with('-') && text != "-" {
            if text.starts_with("--") {
                return Err(format!("unknown option: {text}"));
            }
            for option in text[1..].chars() {
                let metric = match option {
                    'l' => Metric::Lines,
                    'w' => Metric::Words,
                    'c' => Metric::Bytes,
                    'm' => Metric::Chars,
                    'L' => Metric::LongestLine,
                    _ => return Err(format!("unknown option: -{option}")),
                };
                if !metrics.contains(&metric) {
                    metrics.push(metric);
                }
            }
        } else {
            paths.push(arg.clone());
        }
        index += 1;
    }
    if metrics.is_empty() {
        metrics = vec![Metric::Lines, Metric::Words, Metric::Bytes];
    }
    Ok(Options { metrics, paths })
}

fn count_bytes(bytes: &[u8]) -> Counts {
    let text = String::from_utf8_lossy(bytes);
    let longest_line = text.split('\n').map(|line| line.chars().count()).max().unwrap_or(0);
    Counts {
        lines: bytes.iter().filter(|&&byte| byte == b'\n').count(),
        words: text.split_whitespace().count(),
        bytes: bytes.len(),
        chars: text.chars().count(),
        longest_line,
    }
}

fn metric_value(counts: Counts, metric: Metric) -> usize {
    match metric {
        Metric::Lines => counts.lines,
        Metric::Words => counts.words,
        Metric::Bytes => counts.bytes,
        Metric::Chars => counts.chars,
        Metric::LongestLine => counts.longest_line,
    }
}

fn format_counts(counts: Counts, metrics: &[Metric]) -> String {
    metrics
        .iter()
        .map(|&metric| metric_value(counts, metric).to_string())
        .collect::<Vec<_>>()
        .join(" ")
}

fn add_counts(total: &mut Counts, counts: Counts) {
    total.lines = total.lines.saturating_add(counts.lines);
    total.words = total.words.saturating_add(counts.words);
    total.bytes = total.bytes.saturating_add(counts.bytes);
    total.chars = total.chars.saturating_add(counts.chars);
    total.longest_line = total.longest_line.max(counts.longest_line);
}

fn read_input<R: Read>(reader: &mut R) -> io::Result<Counts> {
    let mut bytes = Vec::new();
    reader.read_to_end(&mut bytes)?;
    Ok(count_bytes(&bytes))
}

fn run<I>(args: I) -> i32
where
    I: IntoIterator<Item = OsString>,
{
    let options = match parse_args(args) {
        Ok(options) => options,
        Err(error) => {
            eprintln!("wc: {error}");
            usage();
        }
    };
    let stdin = io::stdin();
    let mut stdin = stdin.lock();
    let stdout = io::stdout();
    let mut stdout = io::BufWriter::new(stdout.lock());
    let inputs = if options.paths.is_empty() {
        vec![(None, None)]
    } else {
        options
            .paths
            .iter()
            .map(|path| {
                if path == OsStr::new("-") {
                    (None, Some(path.as_os_str()))
                } else {
                    (Some(path.as_os_str()), Some(path.as_os_str()))
                }
            })
            .collect()
    };
    let show_names = inputs.len() > 1;
    let mut total = Counts::default();
    let mut status = 0;
    let mut successful_inputs = 0;
    for (path, label) in &inputs {
        let result = match path {
            None => read_input(&mut stdin),
            Some(path) => File::open(path).and_then(|mut file| read_input(&mut file)),
        };
        let counts = match result {
            Ok(counts) => counts,
            Err(error) => {
                let name = label.map_or_else(
                    || "<stdin>".to_string(),
                    |path| path.to_string_lossy().into_owned(),
                );
                eprintln!("wc: {name}: {error}");
                status = 1;
                continue;
            }
        };
        successful_inputs += 1;
        add_counts(&mut total, counts);
        let mut line = format_counts(counts, &options.metrics);
        if show_names {
            line.push(' ');
            line.push_str(&label.expect("multi-input entries have labels").to_string_lossy());
        }
        if let Err(error) = writeln!(stdout, "{line}") {
            eprintln!("wc: stdout: {error}");
            return 1;
        }
    }
    if show_names && successful_inputs > 0 {
        if let Err(error) = writeln!(stdout, "{} total", format_counts(total, &options.metrics)) {
            eprintln!("wc: stdout: {error}");
            status = 1;
        }
    }
    if let Err(error) = stdout.flush() {
        eprintln!("wc: stdout: {error}");
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
    fn counts_lines_words_bytes_and_unicode_chars() {
        let counts = count_bytes("hello 世界\nlast".as_bytes());
        assert_eq!(counts.lines, 1);
        assert_eq!(counts.words, 3);
        assert_eq!(counts.bytes, 17);
        assert_eq!(counts.chars, 13);
        assert_eq!(counts.longest_line, 8);
    }

    #[test]
    fn invalid_utf8_counts_as_replacement_characters() {
        let counts = count_bytes(b"a\xffb");
        assert_eq!(counts.bytes, 3);
        assert_eq!(counts.chars, 3);
        assert_eq!(counts.words, 1);
    }

    #[test]
    fn parses_option_order_and_defaults() {
        let options = parse_args([OsString::from("-mwl"), OsString::from("file")]).unwrap();
        assert_eq!(options.metrics, vec![Metric::Chars, Metric::Words, Metric::Lines]);
        assert_eq!(options.paths, vec![OsString::from("file")]);
        assert_eq!(
            parse_args(std::iter::empty()).unwrap().metrics,
            vec![Metric::Lines, Metric::Words, Metric::Bytes]
        );
    }

    #[test]
    fn reads_from_generic_reader() {
        let mut input = Cursor::new(b"one two\n");
        assert_eq!(read_input(&mut input).unwrap().lines, 1);
    }

    #[test]
    fn formats_selected_metrics() {
        let counts = Counts { lines: 1, words: 2, bytes: 3, chars: 4, longest_line: 5 };
        assert_eq!(format_counts(counts, &[Metric::LongestLine, Metric::Chars]), "5 4");
    }
}
