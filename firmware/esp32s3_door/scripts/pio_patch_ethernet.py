Import("env")

"""ESP32: Ethernet 库 W5100.init() 里的 SPI.begin() 无参会重置引脚，导致 W5500 NoHardware。"""

from pathlib import Path


def patch_w5100():
    root = Path(env["PROJECT_LIBDEPS_DIR"]) / env["PIOENV"] / "Ethernet"
    target = root / "src" / "utility" / "w5100.cpp"
    if not target.exists():
        print("pio_patch_ethernet: skip, missing", target)
        return
    text = target.read_text(encoding="utf-8")
    needle = "\tSPI.begin();\n"
    if "ESP32: keep user SPI.begin" in text:
        print("pio_patch_ethernet: already patched")
        return
    if needle not in text:
        print("pio_patch_ethernet: SPI.begin() pattern not found")
        return
    repl = (
        "#if defined(ESP32)\n"
        "\t// ESP32: keep user SPI.begin(sck,miso,mosi,ss); bare begin() resets pins\n"
        "#else\n"
        "\tSPI.begin();\n"
        "#endif\n"
    )
    target.write_text(text.replace(needle, repl, 1), encoding="utf-8")
    print("pio_patch_ethernet: patched", target)


patch_w5100()
