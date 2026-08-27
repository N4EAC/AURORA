"""Headless tests for Aurora's live Qt radio-audio display path."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel

from audio.buffer import AudioBuffer
from gui.qt_application import AuroraQtWindow


class QtLiveDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.preferences = QSettings(
            str(Path(self.directory.name) / "aurora.ini"), QSettings.IniFormat
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_portaudio_shaped_mono_block_updates_spectrum(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        samples = np.sin(np.arange(1_024, dtype=np.float32) * 0.2)[:, np.newaxis]
        window._receive_audio(AudioBuffer(samples, 12_000))
        window._update_live_display()
        self.assertIsNotNone(window.waterfall._image)
        window.close()

    def test_operator_layout_and_defaults(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        self.assertEqual(window.transmit_button.text(), "SEND")
        self.assertEqual(window.ptt_arm.text(), "PTT Control")
        self.assertTrue(window.ptt_arm.isChecked())
        self.assertEqual(window.reply_channel_enabled.text(), "REPLY CHANNEL: OFF")
        self.assertEqual(window.reply_window.value(), 300)
        self.assertEqual(window.tx_audio_level.value(), 100)
        self.assertEqual(window.tx_test_button.text(), "TUNE / TEST TX")
        self.assertNotIn(
            "Aurora modem center",
            [label.text() for label in window.findChildren(QLabel)],
        )
        self.assertNotIn("#", window.hamlib_model.currentText())
        self.assertIsInstance(window.messages_dock, QDockWidget)
        self.assertIsInstance(window.other_signals_dock, QDockWidget)
        self.assertLessEqual(window.waterfall.maximumHeight(), 72)
        self.assertEqual(
            [action.text() for action in window.menuBar().actions()],
            ["File", "Setup", "View", "Theme", "About"],
        )
        window.close()

    def test_generated_tx_audio_updates_read_only_diagnostics(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.tx_audio_level.setValue(40)
        audio = window._build_transmit_audio("CQ")
        self.assertGreater(len(audio.samples), 0)
        self.assertEqual(window.tx_diagnostics["Audio drive"].text(), "40%")
        self.assertNotEqual(window.tx_diagnostics["Peak"].text(), "--")
        self.assertNotEqual(window.tx_diagnostics["RMS"].text(), "--")
        self.assertEqual(window.tx_diagnostics["Clipping"].text(), "0")
        self.assertEqual(window.tx_diagnostics["Linearity"].text(), "PASS")
        self.assertIn("carriers", window.tx_diagnostics["Profile"].text())
        window.close()

    def test_saved_audio_input_starts_automatically(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        selected = "4: Radio USB Audio"
        window.input_device.addItem(selected)
        window.input_device.setCurrentText(selected)
        window._input_devices[selected] = MagicMock()
        with patch.object(window, "_toggle_receiver") as toggle:
            window._restore_audio_automatically()
        toggle.assert_called_once_with()
        self.assertIn("automatically", window.history.toPlainText())
        window.close()

    def test_missing_saved_audio_input_is_reported_without_starting(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.input_device.setCurrentText("Missing Radio Audio")
        with patch.object(window, "_toggle_receiver") as toggle:
            window._restore_audio_automatically()
        toggle.assert_not_called()
        self.assertIn("unavailable", window.history.toPlainText())
        window.close()

    def test_legacy_tx_drive_is_migrated_without_changing_actual_gain(self) -> None:
        self.preferences.setValue("audio/tx_drive_percent", 55)
        window = AuroraQtWindow(preferences=self.preferences)
        self.assertEqual(window.tx_audio_level.value(), 100)
        self.assertAlmostEqual(window._tx_audio_gain(), 0.55)
        window.close()

    def test_tx_level_test_uses_normal_ptt_playback_path(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window._hamlib = MagicMock()
        device = MagicMock(index=4)
        window.output_device.addItem("Radio Output")
        window.output_device.setCurrentText("Radio Output")
        window._output_devices["Radio Output"] = device
        audio = MagicMock()
        with (
            patch.object(window, "_build_transmit_audio", return_value=audio) as build,
            patch.object(window, "_start_radio_playback") as playback,
        ):
            window._test_tx_audio()
        build.assert_called_once_with("TX LEVEL TEST DE N4EAC")
        playback.assert_called_once_with(audio, 4)
        self.assertIn("observe the radio ALC meter", window.history.toPlainText())
        window._hamlib = None
        window.close()

    def test_view_menu_opens_read_only_signal_diagnostics(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.diagnostics_action.setChecked(True)
        self.assertTrue(window.diagnostics_window.isVisible())
        self.assertIn("SNR", window.diagnostics)
        self.assertIn("Frequency offset", window.diagnostics)
        self.assertIn("Timing offset", window.diagnostics)
        self.assertIn("FEC corrections", window.diagnostics)
        self.assertIsNotNone(window.constellation)
        self.assertIsNotNone(window.subcarrier_quality)
        window.diagnostics_window.hide()
        window.close()

    def test_old_reply_window_default_migrates_to_five_minutes(self) -> None:
        self.preferences.setValue("contact/reply_window_seconds", 120)
        window = AuroraQtWindow(preferences=self.preferences)
        self.assertEqual(window.reply_window.value(), 300)
        window.close()

    def test_active_reply_channel_displays_countdown(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window._contacts.offer(
            local_callsign="N4EAC",
            normal_frequency_hz=7_117_000,
            reply_frequency_hz=7_107_000,
            mode="USB-D",
            window_seconds=300,
        )
        with patch(
            "modem.contact_session.ContactSession.remaining_seconds",
            return_value=185,
        ):
            window._update_contact_countdown()
        self.assertIn("03:05", window.contact_status.text())
        window.close()

    def test_reply_offer_control_has_visible_armed_state(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.reply_frequency.setValue(window.radio_frequency.value() - 1_000)
        window.reply_channel_enabled.setChecked(True)
        self.assertEqual(
            window.reply_channel_enabled.text(), "REPLY CHANNEL: ARMED"
        )
        self.assertEqual(window.contact_status.text(), "REPLY OFFER ARMED")
        window.reply_channel_enabled.setChecked(False)
        self.assertEqual(window.reply_channel_enabled.text(), "REPLY CHANNEL: OFF")
        self.assertEqual(window.contact_status.text(), "SIMPLEX")
        window.close()

    def test_identical_reply_frequency_is_rejected_when_armed(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.reply_frequency.setValue(window.radio_frequency.value())
        window.reply_channel_enabled.setChecked(True)
        self.assertFalse(window.reply_channel_enabled.isChecked())
        self.assertEqual(window.reply_channel_enabled.text(), "REPLY CHANNEL: OFF")
        self.assertEqual(window.contact_status.text(), "REPLY FREQUENCY MUST DIFFER")
        self.assertIn("cannot equal", window.history.toPlainText())
        window.close()

    def test_system_and_chat_messages_use_distinct_theme_safe_colors(self) -> None:
        for theme in ("Dark", "Amber", "Green"):
            window = AuroraQtWindow(preferences=self.preferences)
            window._apply_theme(theme)
            window.history.clear()
            window._append("[CAT] System event")
            window._append("[RX 1500 Hz/W1AW] Hello", chat=True)
            system_cursor = window.history.document().find("System event")
            chat_cursor = window.history.document().find("Hello")
            system_color = system_cursor.charFormat().foreground().color()
            chat_color = chat_cursor.charFormat().foreground().color()
            self.assertTrue(system_color.isValid())
            self.assertTrue(chat_color.isValid())
            self.assertNotEqual(system_color, chat_color)
            window.close()

    def test_hamlib_connection_applies_default_ptt_control_state(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        controller = MagicMock()
        window._cat_events.put(
            ("connected", controller, None, (7_117_000, "USB-D", 2_800, False))
        )
        window._poll_cat_events()
        self.assertTrue(window.ptt_arm.isChecked())
        self.assertTrue(window.transmit_button.isEnabled())
        self.assertTrue(window.station_data_button.isEnabled())
        self.assertIn("SIMPLEX", window.radio_badge.text())
        self.assertIn("RX: 7.117000", window.radio_badge.text())
        self.assertIn("TX: 7.117000", window.radio_badge.text())
        window._contacts.offer(
            local_callsign="K1ABC",
            normal_frequency_hz=7_117_000,
            reply_frequency_hz=7_107_000,
            mode="USB-D",
        )
        window._refresh_radio_route_badge()
        self.assertIn("SPLIT", window.radio_badge.text())
        self.assertIn("RX: 7.107000", window.radio_badge.text())
        self.assertIn("TX: 7.117000", window.radio_badge.text())
        window._hamlib = None
        window.close()

    def test_successful_cat_is_remembered_and_auto_applies_saved_radio(self) -> None:
        self.preferences.setValue("radio/frequency_hz", 7_117_000)
        self.preferences.setValue("radio/mode", "USB-D")
        window = AuroraQtWindow(preferences=self.preferences)
        window._auto_cat_connect_pending = True
        window._startup_radio_settings = (7_117_000, "USB-D")
        controller = MagicMock()
        window._cat_events.put(
            ("connected", controller, None, (145_000_000, "FM", 12_000, False))
        )
        with patch.object(window, "_apply_radio_settings") as apply_settings:
            window._poll_cat_events()
        self.assertTrue(self.preferences.value("cat/last_success", type=bool))
        self.assertEqual(window.radio_frequency.value(), 7_117_000)
        self.assertEqual(window.reply_frequency.value(), 7_117_000)
        self.assertEqual(window.radio_mode.currentText(), "USB-D")
        apply_settings.assert_called_once_with()
        window._hamlib = None
        window.close()

    def test_auto_cat_start_uses_saved_configuration(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        with patch.object(window, "_toggle_cat") as toggle:
            window._restore_cat_automatically()
        self.assertTrue(window._auto_cat_connect_pending)
        toggle.assert_called_once_with()
        window.close()

    def test_legacy_complete_cat_configuration_enables_auto_start(self) -> None:
        self.preferences.setValue("cat/model_id", 1)
        self.preferences.setValue("cat/device", "/dev/cu.usbserial-radio")
        self.preferences.setValue("cat/baud", "9600")
        self.preferences.setValue("cat/external", False)
        window = AuroraQtWindow(preferences=self.preferences)
        self.assertTrue(window._should_restore_cat_automatically())
        window.close()

    def test_untouched_cat_defaults_do_not_enable_auto_start(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        self.assertFalse(window._should_restore_cat_automatically())
        window.close()

    def test_operator_preferences_round_trip(self) -> None:
        first = AuroraQtWindow(preferences=self.preferences)
        first.operator_name.setText("Eduardo")
        first.callsign.setText("K1ABC")
        first.grid.setText("FN31")
        first.latitude.setText("41.1")
        first.longitude.setText("-72.2")
        first.bandwidth.setCurrentText("2.3 kHz")
        first.radio_frequency.setValue(7_074_000)
        first.tx_audio_level.setValue(42)
        first._apply_theme("Amber")
        first.close()

        second = AuroraQtWindow(preferences=self.preferences)
        self.assertEqual(second.operator_name.text(), "Eduardo")
        self.assertEqual(second.callsign.text(), "K1ABC")
        self.assertEqual(second.grid.text(), "FN31")
        self.assertEqual(second.latitude.text(), "41.1")
        self.assertEqual(second.longitude.text(), "-72.2")
        self.assertEqual(second.bandwidth.currentText(), "2.3 kHz")
        self.assertEqual(second.radio_frequency.value(), 7_074_000)
        self.assertEqual(second.tx_audio_level.value(), 42)
        self.assertEqual(second.preferences.value("appearance/theme"), "Amber")
        second.close()

    def test_stale_reply_frequency_is_not_restored_as_split(self) -> None:
        self.preferences.setValue("radio/frequency_hz", 7_111_000)
        self.preferences.setValue("contact/reply_frequency_hz", 7_101_000)
        window = AuroraQtWindow(preferences=self.preferences)
        self.assertEqual(window.radio_frequency.value(), 7_111_000)
        self.assertEqual(window.reply_frequency.value(), 7_111_000)
        self.assertFalse(window.reply_channel_enabled.isChecked())
        self.assertFalse(window.return_normal_button.isEnabled())
        self.assertEqual(window.contact_status.text(), "SIMPLEX")
        self.assertIsNone(self.preferences.value("contact/reply_frequency_hz"))
        window.close()

    def test_other_signal_can_tune_and_prepare_contact(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window._hamlib = MagicMock()
        window.radio_frequency.setValue(14_074_000)
        window.radio_mode.setCurrentText("USB-D")
        window.add_other_signal(1_700, "W1AW", "CQ")
        with patch.object(window, "_request_radio_frequency") as request:
            window._tune_to_other_signal(0, prepare_contact=True)
        self.assertEqual(window.radio_frequency.value(), 14_074_200)
        request.assert_called_once_with(
            14_074_200, "W1AW from 1700 Hz to 1500 Hz"
        )
        self.assertEqual(window.message.text(), "W1AW de <CALL>")
        self.assertIn("Centering W1AW", window.history.toPlainText())
        window.close()

    def test_other_signal_tuning_requires_hamlib(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.add_other_signal(1_700, "W1AW", "CQ")
        window._tune_to_other_signal(0, prepare_contact=False)
        self.assertIn("Connect Hamlib", window.history.toPlainText())
        self.assertEqual(window.radio_frequency.value(), 14_074_000)
        window.close()

    def test_reply_offer_is_accepted_only_by_operator_action(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window._hamlib = MagicMock()
        window.radio_frequency.setValue(7_117_000)
        window.add_other_signal(
            1_500,
            "W1AW",
            "CQ",
            sender_name="Hiram",
            contact_id=42,
            reply_frequency_hz=7_107_000,
            reply_window_seconds=120,
        )
        self.assertIsNone(window._contacts.active)
        with patch.object(window, "_request_radio_frequency") as request:
            window._accept_reply_channel(0)
        session = window._contacts.active
        self.assertIsNotNone(session)
        self.assertEqual(session.receive_frequency_hz, 7_117_000)
        self.assertEqual(session.transmit_frequency_hz, 7_107_000)
        self.assertTrue(window.return_normal_button.isEnabled())
        request.assert_called_once_with(7_117_000, "Reply Channel RX")
        window._hamlib = None
        window.close()

    def test_manual_return_clears_reply_channel_without_radio_or_eoc(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window._contacts.offer(
            local_callsign="K1ABC",
            normal_frequency_hz=7_117_000,
            reply_frequency_hz=7_107_000,
            mode="USB-D",
        )
        window.return_normal_button.setEnabled(True)
        window._return_to_normal_operation()
        self.assertIsNone(window._contacts.active)
        self.assertFalse(window.return_normal_button.isEnabled())
        self.assertEqual(window.contact_status.text(), "SIMPLEX")
        self.assertIn("cleared locally", window.history.toPlainText())
        window.close()

    def test_switching_reply_channel_off_clears_active_split(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.reply_frequency.setValue(window.radio_frequency.value() - 1_000)
        window.reply_channel_enabled.setChecked(True)
        window._contacts.offer(
            local_callsign="K1ABC",
            normal_frequency_hz=7_117_000,
            reply_frequency_hz=7_107_000,
            mode="USB-D",
        )
        window.return_normal_button.setEnabled(True)
        window.reply_channel_enabled.setChecked(False)
        self.assertIsNone(window._contacts.active)
        self.assertFalse(window.return_normal_button.isEnabled())
        self.assertEqual(window.reply_channel_enabled.text(), "REPLY CHANNEL: OFF")
        self.assertEqual(window.contact_status.text(), "SIMPLEX")
        window.close()

    def test_cat_poll_does_not_overwrite_typed_or_pending_frequency(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.radio_frequency.lineEdit().setText("7117000")
        window.radio_frequency.lineEdit().textEdited.emit("7117000")
        window._show_cat_status((14_074_000, "USB-D", 2_800, False))
        self.assertIn("7117000", window.radio_frequency.lineEdit().text())
        window.radio_frequency._operator_edit_finished()
        self.assertTrue(window._operator_tune_pending)
        window._show_cat_status((14_074_000, "USB-D", 2_800, False))
        self.assertEqual(window.radio_frequency.value(), 7_117_000)
        window.close()

    def test_manual_radio_tune_cancels_active_split_without_retuning_radio(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window._hamlib = MagicMock()
        window._contacts.offer(
            local_callsign="N4EAC",
            normal_frequency_hz=7_117_000,
            reply_frequency_hz=7_107_000,
            mode="USB-D",
        )
        window._show_cat_status((7_120_000, "USB-D", 2_800, False))
        self.assertIsNone(window._contacts.active)
        self.assertEqual(window.radio_frequency.value(), 7_120_000)
        self.assertEqual(window.reply_frequency.value(), 7_120_000)
        self.assertIn("MANUAL RADIO TUNE", window.contact_status.text())
        self.assertIn("CANCELLED", window.history.toPlainText())
        window._hamlib = None
        window.close()

    def test_operator_frequency_entry_initializes_reply_frequency(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.reply_frequency.setValue(7_107_000)
        window.radio_frequency.lineEdit().setText("7117")
        window.radio_frequency.lineEdit().textEdited.emit("7117")
        self.assertEqual(window.reply_frequency.value(), 7_117_000)
        self.assertEqual(window.reply_frequency.lineEdit().text(), "7,117,000 Hz")
        self.assertFalse(window._operator_tune_pending)
        window.radio_frequency._operator_edit_finished()
        self.assertEqual(window.radio_frequency.value(), 7_117_000)
        self.assertEqual(window.reply_frequency.value(), 7_117_000)
        self.assertEqual(window.reply_frequency.lineEdit().text(), "7,117,000 Hz")
        window.close()


if __name__ == "__main__":
    unittest.main()
