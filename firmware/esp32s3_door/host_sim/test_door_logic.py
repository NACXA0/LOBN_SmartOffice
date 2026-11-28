"""门脉冲 / DHT 垃圾值 / 鉴权长度规则的主机侧单测。"""

from __future__ import annotations

import unittest

from door_logic import DoorPulseSim, clamp_seconds, is_dht_garbage


class TestClamp(unittest.TestCase):
    def test_bounds(self) -> None:
        self.assertEqual(clamp_seconds(0.05), 0.2)
        self.assertEqual(clamp_seconds(5), 5.0)
        self.assertEqual(clamp_seconds(99), 15.0)


class TestDoorPulse(unittest.TestCase):
    def test_open_close_busy(self) -> None:
        d = DoorPulseSim()
        code, body = d.open("cid-1", 5)
        self.assertEqual(code, 200)
        self.assertEqual(body["result"], "pulsed")
        self.assertTrue(d.relay_on)

        code2, _ = d.open("cid-2", 3)
        self.assertEqual(code2, 409)

        d.tick_release()
        self.assertFalse(d.pulsing)
        code3, body3 = d.close("cid-1")
        self.assertEqual(code3, 200)
        self.assertEqual(body3["result"], "released")

    def test_open_requires_command_id(self) -> None:
        d = DoorPulseSim()
        code, body = d.open("", 5)
        self.assertEqual(code, 400)
        self.assertEqual(body["error"], "bad_command")


class TestDht(unittest.TestCase):
    def test_garbage(self) -> None:
        self.assertTrue(is_dht_garbage(85.0, 0.0))
        self.assertTrue(is_dht_garbage(100.0, 50.0))
        self.assertFalse(is_dht_garbage(24.5, 55.0))


if __name__ == "__main__":
    unittest.main()
