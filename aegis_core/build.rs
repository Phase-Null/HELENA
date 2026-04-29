fn main() {
    if std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default() == "windows" {
        let mut res = winres::WindowsResource::new();
        res.set_manifest_file("aegis.exe.manifest");
        res.compile().unwrap();
    }
}
