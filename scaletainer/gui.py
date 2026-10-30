r"""PySide panel for the container generator.

The panel collects **1:1** dimensions in the unit of your choice plus the
modelling scale, shows the derived scale-space values, and writes the files.
It calls the same :func:`scaletainer.tasks.generate` the command line uses, so the
preview and the result can never disagree.

A whole panel state (dimensions, corrugation, scale, options and optionally the
output settings) can be stored in a JSON file and read back with
:mod:`scaletainer.config`.
"""

from __future__ import annotations

import os

from PySide import QtCore, QtWidgets

from . import config as config_io
from . import tasks
from .params import ContainerParams
from .units import SCALE_PRESETS, UNIT_LABELS, from_mm, to_mm

#: 1:1 dimensions shown in the "Dimensions" tab
DIMENSION_FIELDS = (
    ("length", "Overall length"),
    ("width", "Overall width"),
    ("height", "Overall height"),
    ("frame_size", "End frame / corner fitting width"),
    ("door_frame_width", "Door end border width"),
    ("top_skin", "Roof plate thickness"),
    ("bottom_skin", "Floor plate thickness"),
    ("mount_frame_depth", "Mount rib depth"),
    ("mount_frame_wall", "Mount rib wall thickness"),
    ("mount_frame_chamfer", "Mount rib corner chamfer"),
    ("far_door_plate", "Far door backing plate"),
    ("far_door_rod_width", "Far door locking rod width"),
    ("far_door_gap", "Far door centre seam width"),
    ("far_door_corner", "Far door hinge / handle / casting size"),
)
#: rib groups: (attribute, group title)
RIB_GROUPS = (
    ("side_ribs", "Side wall corrugation"),
    ("top_ribs", "Roof corrugation"),
    ("bottom_ribs", "Floor corrugation"),
    ("door_ribs", "Door end ribs"),
)

#: Common standard container sizes, in 1:1 millimetres:
#: (label, length, width, height).  ISO nominal dimensions plus the reference
#: model's 48 ft box.  Selecting one fills the overall dimension fields.
CONTAINER_SIZES = (
    ("20 ft dry (ISO 1AA)", 6058.0, 2438.0, 2591.0),
    ("20 ft high cube", 6058.0, 2438.0, 2896.0),
    ("20 ft reefer", 6058.0, 2438.0, 2591.0),
    ("40 ft dry (ISO 1BB)", 12192.0, 2438.0, 2591.0),
    ("40 ft high cube (1BB)", 12192.0, 2438.0, 2896.0),
    ("45 ft high cube (1CC)", 13716.0, 2438.0, 2896.0),
    ("48 ft x 8.5 x 9.5 ft (reference)", 14630.4, 2590.8, 2895.6),
    ("53 ft domestic", 16154.0, 2600.0, 2896.0),
)


class _IntBox(QtWidgets.QDoubleSpinBox):
    """Spin box that shows whole units (no decimals) and has no arrows.

    The internal value stays exact -- selecting the reference size keeps
    14630.4 mm -- but the field only ever displays a rounded integer with the
    unit suffix, and the up/down buttons are removed as requested.
    """

    def __init__(self, value: float, unit: str, low: float = 0.0001):
        super().__init__()
        # High internal precision: the spin box clamps its stored value to
        # ``decimals`` places, so a mm<->ft round trip would otherwise drift.
        # The display is overridden below to whole numbers regardless.
        self.setDecimals(6)
        self.setRange(low, 1_000_000.0)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setSuffix(f" {unit}")
        self.setValue(value)

    def textFromValue(self, value: float) -> str:
        return f"{value:.0f}"

    def valueFromText(self, text: str) -> float:
        # Qt hands us the *full* display line, including the prefix/suffix
        # (e.g. "9000 mm").  float() would choke on the unit and the field
        # would silently keep its old value, so strip the decorations first.
        stripped = text.strip()
        prefix, suffix = self.prefix(), self.suffix()
        if prefix and stripped.startswith(prefix):
            stripped = stripped[len(prefix):].strip()
        if suffix and stripped.endswith(suffix):
            stripped = stripped[:-len(suffix)].strip()
        try:
            return float(stripped)
        except ValueError:
            return self.value()


def _float_box(value: float, unit: str, low: float = 0.0001) -> QtWidgets.QDoubleSpinBox:
    box = QtWidgets.QDoubleSpinBox()
    box.setDecimals(4)
    box.setRange(low, 1_000_000.0)
    box.setSingleStep(1.0)
    box.setValue(value)
    box.setSuffix(f" {unit}")
    return box


def _int_box(value: int, high: int = 4000) -> QtWidgets.QSpinBox:
    box = QtWidgets.QSpinBox()
    box.setRange(1, high)
    box.setValue(int(value))
    return box


class ContainerPanel(QtWidgets.QWidget):
    """Non-modal generator panel, intended for the FreeCAD task view."""

    def __init__(self, parent=None, default_directory: str | None = None):
        super().__init__(parent)
        self.reference = ContainerParams.reference()
        self._unit = "mm"
        self._loading = False            # guards against size/combo feedback loops
        self._fields: dict[str, QtWidgets.QDoubleSpinBox] = {}
        self._rib_fields: dict[str, dict[str, QtWidgets.QWidget]] = {}
        self.setWindowTitle("Scaletainer")
        self.setMinimumWidth(580)
        self._preview: tasks.Preview | None = None
        self._stem: str | None = None
        #: the file the panel's values came from / were last saved to
        self.config_path: str | None = None
        self.config_name: str = ""
        #: option toggles a loaded file carried that have no widget here
        self._hidden_options: dict[str, bool] = {}
        #: divider of a scale a file added to the preset list, if any
        self._file_scale: float | None = None
        self._build_ui(default_directory or os.path.expanduser("~/Scaletainer"))
        self._refresh_preview()

    # ------------------------------------------------------------------ UI
    def _build_ui(self, output_dir: str) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        # Configuration files live above the tabs so they are reachable from
        # any tab; the label shows which file the current values came from.
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("Configuration"))
        self.config_name_edit = QtWidgets.QLineEdit()
        self.config_name_edit.setPlaceholderText("optional name, e.g. 48 ft at 1:160")
        self.config_name_edit.setToolTip(
            "Name stored in the configuration file.")
        self.config_name_edit.setText(self.config_name)
        self.config_name_edit.textChanged.connect(self._config_name_edited)
        bar.addWidget(self.config_name_edit, 1)
        self.save_config_button = QtWidgets.QPushButton("Save config...")
        self.save_config_button.setToolTip(
            "Write the dimensions, corrugation, scale, options and output "
            "settings to a JSON file.")
        self.save_config_button.clicked.connect(lambda _: self.save_config())
        bar.addWidget(self.save_config_button)
        self.load_config_button = QtWidgets.QPushButton("Load config...")
        self.load_config_button.setToolTip(
            "Fill the panel from a saved JSON configuration (a generated "
            ".json sidecar also works).")
        self.load_config_button.clicked.connect(lambda _: self.load_config())
        bar.addWidget(self.load_config_button)
        root.addLayout(bar)

        self.config_label = QtWidgets.QLabel("no configuration file")
        self.config_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        root.addWidget(self.config_label)

        tabs = QtWidgets.QTabWidget()
        self.tabs = tabs
        root.addWidget(tabs)
        tabs.addTab(self._dimensions_tab(), "Dimensions (1:1)")
        tabs.addTab(self._ribs_tab(), "Corrugation")
        tabs.addTab(self._scale_tab(), "Scale & options")
        tabs.addTab(self._preview_tab(), "Preview")
        tabs.addTab(self._output_tab(output_dir), "Generate")
        self.status = QtWidgets.QLabel(" ")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def _scale_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)

        self.unit_combo = QtWidgets.QComboBox()
        for key, label in UNIT_LABELS.items():
            self.unit_combo.addItem(label, key)
        self.unit_combo.currentIndexChanged.connect(self._unit_changed)
        form.addRow("Input unit", self.unit_combo)

        self.scale_combo = QtWidgets.QComboBox()
        for label, divider in SCALE_PRESETS.items():
            self.scale_combo.addItem(label, divider)
        self.scale_combo.setCurrentIndex(list(SCALE_PRESETS.values()).index(160.0))
        self.scale_combo.activated.connect(lambda *_: self._refresh_preview())
        form.addRow("Modelling scale", self.scale_combo)

        self.min_feature = _float_box(0.0, "mm", low=0.0)
        self.min_feature.valueChanged.connect(lambda *_: self._refresh_preview())
        form.addRow("Minimum feature size", self.min_feature)

        self.min_pitch = _float_box(0.0, "mm", low=0.0)
        self.min_pitch.valueChanged.connect(lambda *_: self._refresh_preview())
        form.addRow("Minimum rib pitch", self.min_pitch)

        self.inc_mount = QtWidgets.QCheckBox("Build mounting frame ribs")
        self.inc_mount.setChecked(True)
        self.inc_mount.toggled.connect(lambda *_: self._refresh_preview())
        form.addRow("", self.inc_mount)

        self.mount_count = _int_box(self.reference.mount_frame_count, high=50)
        self.mount_count.valueChanged.connect(lambda *_: self._refresh_preview())
        form.addRow("Mounting ribs", self.mount_count)

        hint = QtWidgets.QLabel(
            "Minimum feature size raises any scaled length below it; minimum rib "
            "pitch drops ribs until the pitch is printable. Both are disabled at 0, "
            "which reproduces the reference model exactly.")
        hint.setWordWrap(True)
        form.addRow(hint)
        return page

    def _dimensions_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)

        self.size_combo = QtWidgets.QComboBox()
        self.size_combo.addItem("-- custom / enter manually --")
        for label, length, width, height in CONTAINER_SIZES:
            self.size_combo.addItem(label, (length, width, height))
        self.size_combo.currentIndexChanged.connect(self._apply_container_size)
        form.addRow("Standard size", self.size_combo)

        for name, label in DIMENSION_FIELDS:
            box = _IntBox(from_mm(getattr(self.reference, name), self._unit),
                          self._unit)
            box.valueChanged.connect(lambda *_, n=name: self._dimension_edited(n))
            self._fields[name] = box
            form.addRow(label, box)

        # The panel opens on the reference 48 ft ISO size, which is exactly the
        # dimension values the fields were just filled with.  Selecting it here
        # (guarded so it does not re-fill the fields or refresh the preview mid
        # construction) replaces the old "Restore defaults" button.
        self._loading = True
        self.size_combo.setCurrentIndex(self._size_index_for(
            self.reference.length, self.reference.width, self.reference.height))
        self._loading = False
        return page

    def _dimension_edited(self, name: str) -> None:
        """A manual change to length/width/height drops the standard-size pick."""
        if not self._loading and name in ("length", "width", "height"):
            self._loading = True
            self.size_combo.setCurrentIndex(0)   # "-- custom --"
            self._loading = False
        self._refresh_preview()

    def _apply_container_size(self, index: int) -> None:
        """Fill length/width/height from the selected standard container size."""
        if self._loading:
            return
        data = self.size_combo.itemData(index)
        if not data:
            return                       # the "-- custom --" row
        length, width, height = data
        unit = self._unit
        self._loading = True
        self._fields["length"].setValue(from_mm(length, unit))
        self._fields["width"].setValue(from_mm(width, unit))
        self._fields["height"].setValue(from_mm(height, unit))
        self._loading = False
        self._refresh_preview()

    def _ribs_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        for name, title in RIB_GROUPS:
            pattern = getattr(self.reference, name)
            box = QtWidgets.QGroupBox(title)
            form = QtWidgets.QFormLayout(box)
            fields: dict[str, QtWidgets.QWidget] = {}
            count = _int_box(pattern.count)
            count.valueChanged.connect(lambda *_: self._refresh_preview())
            form.addRow("Rib count", count)
            fields["count"] = count
            for key, label, value in (("slope", "Slope width", pattern.slope),
                                      ("height", "Relief depth", pattern.height)):
                spin = _float_box(from_mm(value, self._unit), self._unit)
                spin.valueChanged.connect(lambda *_: self._refresh_preview())
                form.addRow(label, spin)
                fields[key] = spin
            ratio = QtWidgets.QDoubleSpinBox()
            ratio.setRange(0.0, 1.0)
            ratio.setDecimals(3)
            ratio.setSingleStep(0.05)
            ratio.setValue(pattern.ratio)
            ratio.valueChanged.connect(lambda *_: self._refresh_preview())
            form.addRow("Crest share of flat span", ratio)
            fields["ratio"] = ratio
            self._rib_fields[name] = fields
            layout.addWidget(box)
        layout.addStretch(1)
        return page

    def _preview_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        self.preview_table = QtWidgets.QTableWidget(0, 2)
        self.preview_table.setHorizontalHeaderLabels(["Derived value", "Scale space"])
        self.preview_table.setColumnWidth(0, 230)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.preview_table)
        self.notes = QtWidgets.QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlaceholderText("Adjustments (rib counts, floors) appear here.")
        self.notes.setMaximumHeight(96)
        layout.addWidget(self.notes)
        return page

    def _output_tab(self, output_dir: str) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        row = QtWidgets.QHBoxLayout()
        self.dir_edit = QtWidgets.QLineEdit(output_dir)
        self.dir_edit.setPlaceholderText("Output folder")
        row.addWidget(self.dir_edit, 1)
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        form.addRow("Output folder", row)

        self.format_checks: list[tuple[str, QtWidgets.QCheckBox]] = []
        for key, label in (("fcstd", "FreeCAD document (.FCStd)"),
                           ("step", "STEP (.step)"),
                           ("stl", "STL (.stl)"),
                           ("3mf", "3MF (.3mf)")):
            check = QtWidgets.QCheckBox(label)
            check.setChecked(key in ("fcstd", "stl"))
            self.format_checks.append((key, check))
            form.addRow(check)

        self.parts_check = QtWidgets.QCheckBox("Also write one file per component")
        self.parts_check.setChecked(True)
        form.addRow(self.parts_check)

        # A configuration file remembers these too, so they get their own
        # "remember output settings" row rather than being reset on load.
        self.remember_export = QtWidgets.QCheckBox(
            "Save output folder, formats and parts option in config files")
        self.remember_export.setToolTip(
            "On: a config file also stores the output settings below.\n"
            "Off: only the dimensions, corrugation, scale and options are saved.")
        self.remember_export.setChecked(True)
        form.addRow(self.remember_export)

        buttons = QtWidgets.QHBoxLayout()
        self.generate_button = QtWidgets.QPushButton("Generate container")
        self.generate_button.setDefault(True)
        self.generate_button.clicked.connect(self.generate)
        buttons.addWidget(self.generate_button)
        form.addRow(buttons)
        return page

    # --------------------------------------------------------------- state
    def _scale_divider(self) -> float:
        return float(self.scale_combo.currentData())

    def input_values(self) -> dict:
        """Panel content as the plain dict :mod:`scaletainer.tasks` expects."""
        values = {name: float(box.value()) for name, box in self._fields.items()}
        for name, fields in self._rib_fields.items():
            values[name] = {
                "count": int(fields["count"].value()),
                "slope": float(fields["slope"].value()),
                "ratio": float(fields["ratio"].value()),
                "height": float(fields["height"].value()),
            }
        values["mount_frame_count"] = int(self.mount_count.value())
        values["scale_divider"] = self._scale_divider()
        values["min_feature_mm"] = float(self.min_feature.value())
        values["min_rib_pitch_mm"] = float(self.min_pitch.value())
        values["include_mount_frame"] = self.inc_mount.isChecked()
        # options without a widget here (kept from a loaded file)
        values.update(self._hidden_options)
        return values

    def selected_formats(self) -> tuple[str, ...]:
        chosen = tuple(key for key, cb in self.format_checks if cb.isChecked())
        return chosen or ("fcstd", "stl")

    def output_directory(self) -> str:
        return os.path.expanduser(self.dir_edit.text().strip() or ".")

    # ------------------------------------------------------ config files
    def export_options(self) -> config_io.ExportOptions:
        """The Generate-tab output settings stored alongside a configuration."""
        return config_io.ExportOptions(
            directory=self.dir_edit.text().strip() or None,
            formats=self.selected_formats(),
            separate_parts=self.parts_check.isChecked())

    def config(self, name: str | None = None) -> config_io.ContainerConfig:
        """Snapshot the whole panel as a :class:`config_io.ContainerConfig`."""
        export = self.export_options() if self.remember_export.isChecked() else None
        return config_io.build(self.input_values(), self._unit, export,
                               name=name if name is not None else self.config_name)

    def _default_config_name(self) -> str:
        """Suggested file name for Save config, without stray dots.

        The 1:1 fields store exact values (``14630.4``), but a name full of
        decimal points reads as a file extension, so the suggested name rounds
        the size like the fields display it and spells the scale with a dash.
        """
        values = self.input_values()
        size = "x".join(f"{round(float(values[k])):d}"
                        for k in ("length", "width", "height"))
        scale = f"{float(values['scale_divider']):g}".replace(".", "-")
        return config_io.with_extension(f"container-{size}-1-{scale}")

    def _config_name_edited(self, text: str) -> None:
        self.config_name = text.strip()
        self._update_config_label()

    def _update_config_label(self) -> None:
        if self.config_path:
            name = f"{self.config_name} - " if self.config_name else ""
            self.config_label.setText(f"{name}{self.config_path}")
            self.config_label.setToolTip(self.config_path)
        else:
            self.config_label.setText("no configuration file")
            self.config_label.setToolTip("Save or load the panel values as JSON")

    def apply_config(self, cfg: config_io.ContainerConfig,
                     path: str | None = None) -> list[str]:
        """Fill every widget from a loaded configuration.

        Returns the keys whose value was outside a widget's range and therefore
        clamped.

        The file's input unit is adopted as-is: its numbers were typed in that
        unit, so they are written straight into the fields instead of being
        converted through the unit combo (which would rescale them).
        """
        unit = cfg.unit if cfg.unit in UNIT_LABELS else "mm"
        values = cfg.values
        self._loading = True
        try:
            index = self.unit_combo.findData(unit)
            if index >= 0:
                self.unit_combo.setCurrentIndex(index)
            self._unit = unit
            for box in self._fields.values():
                box.setSuffix(f" {unit}")
            for fields in self._rib_fields.values():
                for key in ("slope", "height"):
                    fields[key].setSuffix(f" {unit}")

            for name, box in self._fields.items():
                value = values.get(name)
                if value is None:
                    value = from_mm(getattr(self.reference, name), unit)
                box.setValue(float(value))

            for name, fields in self._rib_fields.items():
                pattern = values.get(name)
                if pattern is None:      # file omits this rib set: keep reference
                    ref = getattr(self.reference, name)
                    pattern = {"count": ref.count, "slope": ref.slope,
                               "ratio": ref.ratio, "height": ref.height}
                fields["count"].setValue(int(pattern["count"]))
                fields["slope"].setValue(float(pattern["slope"]))
                fields["height"].setValue(float(pattern["height"]))
                fields["ratio"].setValue(float(pattern["ratio"]))

            if values.get("mount_frame_count") is not None:
                self.mount_count.setValue(int(values["mount_frame_count"]))
            else:
                self.mount_count.setValue(self.reference.mount_frame_count)

            self._select_scale(values.get("scale_divider"))
            self.min_feature.setValue(float(values.get("min_feature_mm") or 0.0))
            self.min_pitch.setValue(float(values.get("min_rib_pitch_mm") or 0.0))
            if values.get("include_mount_frame") is not None:
                self.inc_mount.setChecked(bool(values["include_mount_frame"]))
            # toggles with no widget here are kept so generate() honours them
            self._hidden_options = {
                key: bool(values[key])
                for key in ("include_door_side", "include_far_door")
                if values.get(key) is not None}

            if cfg.export is not None:
                export = cfg.export
                if export.directory:
                    self.dir_edit.setText(export.directory)
                if export.formats:
                    chosen = set(export.formats)
                    for key, check in self.format_checks:
                        check.setChecked(key in chosen)
                if export.separate_parts is not None:
                    self.parts_check.setChecked(bool(export.separate_parts))

            self.config_name = cfg.name or ""
            self.config_name_edit.setText(self.config_name)
            self.config_path = os.path.abspath(os.path.expanduser(path)) if path else None
            # the loaded length/width/height may still match a standard size
            # (_size_index_for compares against 1:1 millimetres)
            self.size_combo.setCurrentIndex(self._size_index_for(
                *[to_mm(float(self._fields[k].value()), unit)
                  for k in ("length", "width", "height")]))
        finally:
            self._loading = False
        self._update_config_label()
        self._refresh_preview()
        return self._clamped_keys(cfg)

    def _config_widgets(self) -> dict[str, QtWidgets.QSpinBox]:
        """Every widget a configuration value is written into."""
        widgets: dict[str, QtWidgets.QSpinBox] = dict(self._fields)
        for name, fields in self._rib_fields.items():
            for key, box in fields.items():
                widgets[f"{name}.{key}"] = box
        widgets["mount_frame_count"] = self.mount_count
        widgets["min_feature_mm"] = self.min_feature
        widgets["min_rib_pitch_mm"] = self.min_pitch
        return widgets

    def _clamped_keys(self, cfg: config_io.ContainerConfig) -> list[str]:
        """File values outside a widget's range, which Qt silently clamps."""
        widgets = self._config_widgets()
        out = []
        for key, wanted in sorted(cfg.values.items()):
            if isinstance(wanted, dict):
                for field, value in wanted.items():
                    box = widgets.get(f"{key}.{field}")
                    if box is not None and not box.minimum() <= value <= box.maximum():
                        out.append(f"{key}.{field}")
                continue
            box = widgets.get(key)
            if box is not None and not box.minimum() <= wanted <= box.maximum():
                out.append(key)
        return out

    def _select_scale(self, divider) -> None:
        """Pick the preset for *divider*, adding it to the combo when new.

        A scale that is not one of the presets (from the console or a hand
        written file) is kept rather than snapping to a preset.  Only one such
        entry exists at a time, so loading several files cannot fill the list.
        """
        if divider is None:
            return
        divider = float(divider)
        if self._file_scale is not None:
            stale = self.scale_combo.findData(self._file_scale)
            if stale >= 0:
                self.scale_combo.removeItem(stale)
            self._file_scale = None
        index = self.scale_combo.findData(divider)
        if index < 0:
            self.scale_combo.addItem(f"1:{divider:g} (from file)", divider)
            index = self.scale_combo.findData(divider)
            self._file_scale = divider
        self.scale_combo.setCurrentIndex(index)

    def save_config(self, path: str | None = None, name: str | None = None) -> str | None:
        """Write the panel to a JSON file; asks for a path when none is given."""
        if name is not None:
            self.config_name = name
        if not path:
            start = self.config_path or os.path.join(
                self.output_directory(), self._default_config_name())
            chosen, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save container configuration", start,
                "Container configuration (*.json);;All files (*)")
            if not chosen:
                return None
            path = chosen
        try:
            written = config_io.write(self.config(),
                                      config_io.with_extension(
                                          os.path.expanduser(path)))
        except (config_io.ConfigError, OSError) as exc:
            self.status.setText(f"Could not save configuration: {exc}")
            return None
        self.config_path = written
        self._update_config_label()
        self.status.setText(f"Saved configuration to {written}.")
        return written

    def load_config(self, path: str | None = None) -> config_io.ContainerConfig | None:
        """Read a JSON file into the panel; asks for one when none is given."""
        if not path:
            start = self.config_path or self.output_directory()
            chosen, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Load container configuration", start,
                "Container configuration (*.json);;All files (*)")
            if not chosen:
                return None
            path = chosen
        try:
            cfg = config_io.load(path)
        except config_io.ConfigError as exc:
            self.status.setText(f"Could not load configuration: {exc}")
            return None
        clamped = self.apply_config(cfg, path)
        message = f"Loaded {cfg.describe()}."
        if clamped:
            # Qt clamps out-of-range values silently, so say which field moved
            message += (" Some values are outside the field limits and were "
                        "clamped: " + ", ".join(clamped) + ".")
        self.status.setText(message)
        return cfg

    def _unit_changed(self, _index: int) -> None:
        """Re-express every 1:1 field in the new unit, keeping the model size."""
        old, new = self._unit, str(self.unit_combo.currentData())
        self._unit = new
        if self._loading:
            # a load sets the fields from the file itself: no re-conversion
            return
        self._loading = True             # programmatic change: keep size selected
        for box in self._fields.values():
            box.setSuffix(f" {new}")
            box.setValue(from_mm(to_mm(box.value(), old), new))
        for fields in self._rib_fields.values():
            for key in ("slope", "height"):
                box = fields[key]
                box.setSuffix(f" {new}")
                box.setValue(from_mm(to_mm(box.value(), old), new))
        self._loading = False
        self._refresh_preview()

    def _size_index_for(self, length: float, width: float, height: float) -> int:
        """Combo index of the standard size matching these 1:1 lengths, or 0."""
        for i in range(self.size_combo.count()):
            data = self.size_combo.itemData(i)
            if data and all(abs(a - b) < 0.5 for a, b in zip(data, (length, width, height))):
                return i
        return 0

    def _reset_dimensions(self) -> None:
        unit = self._unit
        self._loading = True
        for name, box in self._fields.items():
            box.setValue(from_mm(getattr(self.reference, name), unit))
        for name, fields in self._rib_fields.items():
            pattern = getattr(self.reference, name)
            fields["count"].setValue(pattern.count)
            fields["slope"].setValue(from_mm(pattern.slope, unit))
            fields["height"].setValue(from_mm(pattern.height, unit))
            fields["ratio"].setValue(pattern.ratio)
        self.mount_count.setValue(self.reference.mount_frame_count)
        self._loading = False
        # reflect the restored size in the dropdown when it is a known standard
        self.size_combo.setCurrentIndex(self._size_index_for(
            self.reference.length, self.reference.width, self.reference.height))
        self._refresh_preview()

    def restore_defaults(self) -> None:
        """Reset the whole panel: 1:1 dimensions, scale and options."""
        self.unit_combo.setCurrentIndex(0)
        self._reset_dimensions()
        # also drops a "(from file)" entry a loaded config may have added
        self._select_scale(160.0)
        self.min_feature.setValue(0.0)
        self.min_pitch.setValue(0.0)
        self.inc_mount.setChecked(True)
        self._hidden_options = {}
        self.config_name = ""
        self.config_name_edit.setText("")
        self.config_path = None      # the panel no longer matches any file
        self._update_config_label()
        self._refresh_preview()

    def _browse(self) -> None:
        start = self.output_directory()
        # unlike getSaveFileName/getOpenFileName this returns a plain str, not
        # a (path, filter) tuple -- unpacking it raised and left the field alone
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Output folder", start)
        if chosen:
            self.dir_edit.setText(chosen)

    # ------------------------------------------------------------- actions
    def preview_data(self) -> "tasks.Preview | None":
        """The last successfully derived preview, or ``None``."""
        return self._preview

    def preview_rows(self) -> list[tuple[str, str]]:
        """The derived values currently shown in the table."""
        return self._preview.rows() if self._preview else []

    def _refresh_preview(self) -> None:
        try:
            data = tasks.preview(self.input_values(), self._unit)
        except Exception as exc:  # noqa: BLE001 - report anything in the panel
            self._preview = None
            self.status.setText(f"Invalid parameters: {exc}")
            return
        self._preview = data
        rows = data.rows()
        self.preview_table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            self.preview_table.setItem(i, 0, QtWidgets.QTableWidgetItem(label))
            self.preview_table.setItem(i, 1, QtWidgets.QTableWidgetItem(value))
        self.notes.setPlainText("\n".join(data.notes))
        self.status.setText(
            f"At {data.scale} the container is {data.length:.2f} x "
            f"{data.width:.2f} x {data.height:.2f} mm.")

    def generate(self) -> None:
        """Build the model and write the requested files."""
        self.status.setText("Generating...")
        QtWidgets.QApplication.processEvents()
        try:
            result = tasks.generate(
                self.input_values(), self.output_directory(), unit=self._unit,
                formats=self.selected_formats(),
                separate_parts=self.parts_check.isChecked(),
                progress=lambda m: (self.status.setText(m),
                                    QtWidgets.QApplication.processEvents()))
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Generation failed: {exc}")
            return
        self._stem = result.stem
        self.status.setText(
            f"Wrote {len(result.files)} files to {result.directory} ({result.stem}).")


def create_panel(directory: str | None = None) -> ContainerPanel:
    return ContainerPanel(default_directory=directory)
