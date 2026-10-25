#!/usr/bin/env python3
"""METMC Display Settings for Phosh: output mode, output scale, text and app-grid icon size."""
import os
import re
import shutil
import subprocess
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

APP_NAME = "METMC Display Settings"

def run(args):
    try:
        return subprocess.run(args, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=False)
    except OSError as exc:
        return None

class DisplaySettings(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_NAME)
        self.set_default_size(420, 620)
        self.set_border_width(16)
        self.set_position(Gtk.WindowPosition.CENTER)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(outer)
        heading = Gtk.Label()
        heading.set_markup("<big><b>Display &amp; Appearance</b></big>")
        heading.set_xalign(0)
        outer.pack_start(heading, False, False, 0)
        intro = Gtk.Label(label="Adjust display modes and interface sizing. Some appearance changes apply after restarting Phosh.")
        intro.set_line_wrap(True)
        intro.set_xalign(0)
        outer.pack_start(intro, False, False, 0)

        self.output = Gtk.ComboBoxText()
        self.mode = Gtk.ComboBoxText()
        self.scale = Gtk.ComboBoxText()
        self.text_scale = Gtk.ComboBoxText()
        self.icon_size = Gtk.ComboBoxText()
        self.status = Gtk.Label()
        self.status.set_line_wrap(True)
        self.status.set_xalign(0)

        self._add_row(outer, "Display", self.output)
        self._add_row(outer, "Resolution / refresh rate", self.mode)
        self._add_row(outer, "Display scale", self.scale)
        self._add_row(outer, "Text size", self.text_scale)
        self._add_row(outer, "App-grid icon size", self.icon_size)

        for value in ["0.75", "1.0", "1.25", "1.5", "1.75", "2.0"]:
            self.scale.append_text(value + "×")
        self.scale.set_active(1)
        for value, label in [("0.8", "Small"), ("1.0", "Default"), ("1.15", "Large"),
                             ("1.3", "Extra large"), ("1.5", "Huge")]:
            self.text_scale.append(value, label)
        self.text_scale.set_active_id("1.0")
        for value, label in [("48", "Small (48 px)"), ("56", "Medium (56 px)"),
                             ("64", "Large (64 px)"), ("72", "Extra large (72 px)"),
                             ("88", "Huge (88 px)")]:
            self.icon_size.append(value, label)
        self.icon_size.set_active_id("64")

        apply_btn = Gtk.Button(label="Apply changes")
        apply_btn.set_size_request(-1, 48)
        apply_btn.connect("clicked", self.apply)
        outer.pack_start(apply_btn, False, False, 0)
        outer.pack_start(self.status, False, False, 0)
        self.refresh_outputs()

    def _add_row(self, parent, title, control):
        label = Gtk.Label(label=title)
        label.set_xalign(0)
        parent.pack_start(label, False, False, 0)
        control.set_size_request(-1, 44)
        parent.pack_start(control, False, False, 0)

    def refresh_outputs(self):
        self.output.remove_all()
        self.mode.remove_all()
        if not shutil.which("wlr-randr"):
            self.status.set_text("wlr-randr is not installed. Resolution controls require a Wayland compositor with output-management support.")
            return
        result = run(["wlr-randr"])
        if not result or result.returncode != 0:
            self.status.set_text("Could not read display modes. Make sure this app is running inside the Phoc Wayland session.")
            return
        self.outputs = {}
        current = None
        for line in result.stdout.splitlines():
            if line and not line[0].isspace() and ":" in line:
                current = line.split(":", 1)[0].strip()
                self.outputs[current] = []
            elif current and line.strip():
                m = re.match(r"\s+(\d+x\d+(?:@\d+(?:\.\d+)?Hz)?)(?:\s+\(current\))?", line)
                if m:
                    self.outputs[current].append(m.group(1))
        for name in self.outputs:
            self.output.append_text(name)
        if self.output.get_model() and len(self.outputs):
            self.output.set_active(0)
            self.output.connect("changed", self.on_output_changed)
            self.on_output_changed(self.output)

    def on_output_changed(self, combo):
        name = combo.get_active_text()
        self.mode.remove_all()
        if not name:
            return
        for item in self.outputs.get(name, []):
            self.mode.append_text(item)
        if self.mode.get_model() and len(self.outputs.get(name, [])):
            self.mode.set_active(0)

    def apply(self, _button):
        messages = []
        output = self.output.get_active_text()
        mode = self.mode.get_active_text()
        scale_text = self.scale.get_active_text()
        if output and mode and shutil.which("wlr-randr"):
            # Keep all changes explicit; do not alter compositor configuration files.
            result = run(["wlr-randr", "--output", output, "--mode", mode])
            if result and result.returncode == 0:
                scale_value = scale_text.replace("×", "") if scale_text else "1.0"
                result = run(["wlr-randr", "--output", output, "--scale", scale_value])
            if result and result.returncode == 0:
                messages.append("Display mode and scale applied.")
            else:
                detail = result.stderr.strip() if result else "wlr-randr could not start"
                messages.append("Display change failed: " + detail)
        elif not shutil.which("wlr-randr"):
            messages.append("Install wlr-randr to change resolution.")

        text_id = self.text_scale.get_active_id()
        if text_id:
            result = run(["gsettings", "set", "org.gnome.desktop.interface",
                          "text-scaling-factor", text_id])
            messages.append("Text size updated." if result and result.returncode == 0
                            else "Could not update text size (GSettings schema may be unavailable).")

        icon_id = self.icon_size.get_active_id()
        if icon_id:
            # GTK CSS is user-scoped and only targets Phosh's app grid.
            config_dir = os.path.expanduser("~/.config/gtk-3.0")
            css_path = os.path.join(config_dir, "gtk.css")
            os.makedirs(config_dir, exist_ok=True)
            marker_start = "/* METMC display settings: app-grid icons start */"
            marker_end = "/* METMC display settings: app-grid icons end */"
            existing = ""
            try:
                with open(css_path, "r", encoding="utf-8") as stream:
                    existing = stream.read()
            except FileNotFoundError:
                pass
            existing = re.sub(re.escape(marker_start) + r".*?" + re.escape(marker_end),
                              "", existing, flags=re.S).rstrip()
            block = (f"\n\n{marker_start}\n"
                     f"phosh-app-grid image, .phosh-app-grid image {{\n"
                     f"  min-width: {icon_id}px; min-height: {icon_id}px;\n"
                     f"}}\n{marker_end}\n")
            with open(css_path, "w", encoding="utf-8") as stream:
                stream.write(existing + block)
            messages.append("App-grid icon sizing saved; restart Phosh to reload GTK CSS.")
        self.status.set_text("\n".join(messages) or "No changes were selected.")

win = DisplaySettings()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
