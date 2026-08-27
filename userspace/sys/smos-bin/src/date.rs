use std::ffi::CString;

#[repr(C)]
struct Tm {
    sec: i32,
    min: i32,
    hour: i32,
    mday: i32,
    mon: i32,
    year: i32,
    wday: i32,
    yday: i32,
    isdst: i32,
}

#[repr(C)]
struct Timespec {
    tv_sec: i64,
    tv_nsec: i64,
}

unsafe extern "C" {
    fn clock_gettime(clock_id: i32, result: *mut Timespec) -> i32;
    fn localtime_r(time: *const i64, result: *mut Tm) -> *mut Tm;
    fn gmtime_r(time: *const i64, result: *mut Tm) -> *mut Tm;
    fn strftime(buf: *mut u8, size: usize, format: *const i8, tm: *const Tm) -> usize;
}

const CLOCK_REALTIME: i32 = 0;

fn usage() -> ! {
    eprintln!("Usage: date [-u] [-d time] [+format]");
    std::process::exit(1);
}

fn main() {
    let mut utc = false;
    let mut timestamp = 0i64;
    let mut timestamp_from_argument = false;
    let mut format = "%c".to_string();
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        match args[i].to_str() {
            Some("-u") => utc = true,
            Some("-d") => {
                i += 1;
                timestamp = args
                    .get(i)
                    .and_then(|s| s.to_str())
                    .and_then(|s| s.parse().ok())
                    .unwrap_or_else(|| usage());
                timestamp_from_argument = true;
            }
            Some(s) if s.starts_with('+') && i + 1 == args.len() => format = s[1..].to_string(),
            _ => usage(),
        }
        i += 1;
    }
    if !timestamp_from_argument {
        let mut wall_clock = Timespec { tv_sec: 0, tv_nsec: 0 };
        if unsafe { clock_gettime(CLOCK_REALTIME, &mut wall_clock) } != 0 {
            eprintln!("date: wall clock unavailable");
            std::process::exit(1);
        }
        timestamp = wall_clock.tv_sec;
    }
    let mut tm =
        Tm { sec: 0, min: 0, hour: 0, mday: 0, mon: 0, year: 0, wday: 0, yday: 0, isdst: 0 };
    let ptr = unsafe {
        if utc {
            gmtime_r(&timestamp, &mut tm)
        } else {
            localtime_r(&timestamp, &mut tm)
        }
    };
    if ptr.is_null() {
        eprintln!("date: time failed");
        std::process::exit(1);
    }
    let fmt = CString::new(format).unwrap_or_else(|_| usage());
    let mut out = vec![0u8; 256];
    let n = unsafe { strftime(out.as_mut_ptr(), out.len(), fmt.as_ptr().cast(), &tm) };
    if n == 0 {
        eprintln!("date: format failed");
        std::process::exit(1);
    }
    println!("{}", String::from_utf8_lossy(&out[..n]));
}
