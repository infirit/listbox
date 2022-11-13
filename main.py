import cairo
import os
from datetime import datetime

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from typing import Dict, Optional
from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import GdkPixbuf
from blueman.bluez.Adapter import Adapter
from blueman.bluez.Battery import Battery
from blueman.bluez.Device import Device
from blueman.bluez.Manager import Manager
from blueman.DeviceClass import get_minor_class, get_major_class, gatt_appearance_to_name
from _blueman import ConnInfoReadError, conn_info

OLD_CSS = b"""
/*levelbar#tpl_levelbar block.filled {
  background-color: #3465a3;
  border-color: #3465a3;
}*/
"""

CSS = b"""
levelbar trough {
  padding: 1px;
}

levelbar#battery_levelbar block.filled {
  background-color: grey;
  border-color: grey;
}

levelbar#rssi_levelbar block.filled {
  background-color: orange;
  border-color: orange;
}
"""


DEVICEMENU = """
<interface>
  <menu id="devicemenu">
    <section>
      <item>
        <attribute name="label" translatable="yes">Connect</attribute>
        <attribute name="action">app.connect</attribute>
        <attribute name="icon">bluetooth-symbolic</attribute>
      </item>
      <item>
        <attribute name="label" translatable="yes">Pair</attribute>
        <attribute name="action">app.pair</attribute>
        <attribute name="icon">blueman-pair-symbolic</attribute>
      </item>
    </section>
  </menu>
</interface>
"""


class DeviceListBoxRow(Gtk.ListBoxRow):
    def __init__(self, device: Device, window, scale):
        super().__init__(visible=True)
        self.device: Optional[Device] = device
        self.battery: Optional[Battery] = None
        self.row_created: datetime = datetime.now()
        self.object_path: str = device.get_object_path()
        self.device.connect_signal("property-changed", self.on_property_changed)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS)
        stylecontext = self.get_style_context()
        screen = Gdk.Screen.get_default()
        stylecontext.add_provider_for_screen(screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.builder = Gtk.Builder.new_from_file("blueman_listbox_recreated.ui")

        self.row_revealer = self.builder.get_object("row_revealer")
        self.add(self.row_revealer)

        self.ic = Gtk.IconTheme.get_default()
        self.set_device_icon(device['Icon'])

        for prop in device.get_properties():
            self.on_property_changed(device, prop, device[prop], self.object_path)

        self.detailrevealer = self.builder.get_object("detail_revealer")

    def add_battery(self, obj_path):
        return
        if self.battery is not None:
            return
        self.battery = Battery(obj_path=obj_path)
        self.battery.connect_signal("property-changed", self.on_property_changed)
        self.on_property_changed(self.battery, "Percentage", self.battery["Percentage"], self.object_path)
        self.builder_object_method("battery_revealer", "set_reveal_child", self.device["Connected"])
        print(f"Set battery to {self.battery['Percentage']}")

    def _set_device_description(self):
        klass = get_minor_class(self.device['Class'])
        # Bluetooth >= 4 devices use Appearance property
        appearance = self.device["Appearance"]
        if klass not in ("Uncategorized", "Unknown"):
            description = klass
        elif klass == "Unknown" and appearance:
            description = gatt_appearance_to_name(appearance)
        else:
            description = get_major_class(self.device['Class'])
        lbl = f"<span size='small'>{description}{' - Connected' if self.device['Connected'] else ''}</span>"
        self.builder_object_method("appearance_label", "set_markup", lbl)

    def _setup_level_monitor(self):
        pass

    def _update_levels(self):
        cinfo = conn_info(self.device["Address"], os.path.basename(self.device["Adapter"]))
        try:
            cinfo.init()
        except ConnInfoReadError:
            print("Failed to get power levels, probably a LE device.")

        if not cinfo.failed:
            rssi_raw = cinfo.get_rssi()
            rssi_val = max(50 + float(rssi_raw) / 127 * 50, 10)
            tpl_val = max(50 + float(cinfo.get_tpl()) / 127 * 50, 10)

            w = 14 # * self.get_scale_factor()
            h = 48 # * self.get_scale_factor()

            pixmap_path = "/usr/share/blueman/pixmaps/"
            rssi_path = os.path.join(pixmap_path, f"blueman-rssi-{int(round(rssi_val, -1))}.png")
            rssi_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(rssi_path, w, h, True)
            self.builder_object_method("rssi_image", "set_from_pixbuf", rssi_pb)

            tpl_path = os.path.join(pixmap_path, f"blueman-tpl-{int(round(tpl_val, -1))}.png")
            tpl_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(tpl_path, w, h, True)
            self.builder_object_method("tpl_image", "set_from_pixbuf", tpl_pb)

            print(f"raw values: rssi {rssi_raw} tpl {tpl_val}")
            #self.builder_object_method("rssi_levelbar", "set_value", rssi_val)
            #self.builder_object_method("tpl_levelbar", "set_value", tpl_val)

        self.builder_object_method("rssi_revealer", "set_reveal_child", self.device["Connected"])
        #self.builder_object_method("rssi_label", "set_markup", f"<span size='small'>RSSI {rssi_val}</span>")
        self.builder_object_method("tpl_revealer", "set_reveal_child", self.device["Connected"])

    def set_device_icon(self, icon_name):
        window = self.get_window()
        scale = self.get_scale_factor()
        icon_info = self.ic.lookup_icon_for_scale(icon_name, 48, scale, Gtk.IconLookupFlags.FORCE_SIZE)
        target = icon_info.load_surface(window)
        ctx = cairo.Context(target)

        if self.device["Paired"]:
            _icon_info = self.ic.lookup_icon_for_scale("blueman-paired-emblem", 16, scale,
                                                       Gtk.IconLookupFlags.FORCE_SIZE)
            paired_surface = _icon_info.load_surface(window)
            ctx.set_source_surface(paired_surface, 1 / scale, 1 / scale)
            ctx.paint_with_alpha(0.8)

        if self.device["Trusted"]:
            _icon_info = self.ic.lookup_icon_for_scale("blueman-trusted-emblem", 16, scale,
                                                       Gtk.IconLookupFlags.FORCE_SIZE)
            trusted_surface = _icon_info.load_surface(window)
            height = target.get_height()
            mini_height = trusted_surface.get_height()
            y = height / scale - mini_height / scale - 1 / scale

            ctx.set_source_surface(trusted_surface, 1 / scale, y)
            ctx.paint_with_alpha(0.8)

        if self.device["Blocked"]:
            _icon_info = self.ic.lookup_icon_for_scale("blueman-blocked-emblem", 16, scale,
                                                       Gtk.IconLookupFlags.FORCE_SIZE)
            blocked_surface = _icon_info.load_surface(window)
            width = target.get_width()
            ctx.set_source_surface(blocked_surface, width - (1 + 16) / scale, 1 / scale)
            ctx.paint_with_alpha(0.8)

        self.builder_object_method("device_icon", "set_from_surface", target)

    @property
    def selected(self) -> bool:
        return self.is_selected()

    def reveal_row(self, state):
        if state:
            self.show_all()
        self.row_revealer.set_reveal_child(state)

    def reveal_detail(self, state):
        pass
        print(f"reveal state {state}")
        self.detailrevealer.set_reveal_child(state)

    def on_property_changed(self, _device, key, val, obj_path):
        print(f"{key} {val} {obj_path}")
        if key == "Alias":
            self.builder_object_method("alias_label", "set_markup", f"<span size='large'>{val}</span>")
        elif key == "Paired":
            self.set_device_icon(self.device["Icon"])
            #lbl = f"<span size='small'>{'Yes' if val else 'No'}</span>"
            #self.builder_object_method("paired_label", "set_opacity", 1.0 if val else 0.5)
            #self.builder_object_method("paired_label", "set_markup", lbl)
        elif key == "Connected":
            self._set_device_description()
            self._update_levels()
        elif key == "Trusted":
            self.set_device_icon(self.device["Icon"])
            #lbl = f"<span size='small'>{'Yes' if val else 'No'}</span>"
            #self.builder_object_method("trusted_label", "set_opacity", 1.0 if val else 0.5)
            #self.builder_object_method("trusted_label", "set_markup", lbl)
        elif key == "Blocked":
            self.set_device_icon(self.device["Icon"])
            #lbl = f"<span size='small'>{'Yes' if val else 'No'}</span>"
            #self.builder_object_method("blocked_label", "set_opacity", 1.0 if val else 0.5)
            #self.builder_object_method("blocked_label", "set_markup", lbl)
        elif key == "Address":
            lbl = f"<span size='small'>{val}</span>"
            self.builder_object_method("btaddress_label", "set_markup", lbl)
        elif key == "Adapter":
            hci = val.split("/")[-1]
            adapter = Adapter(obj_path=val)
            lbl = f"<span size='small'>{adapter['Name']} ({hci})</span>"
            #self.builder_object_method("adapter_label", "set_markup", lbl)
        elif key in ("Class", "Appearance"):
            self._set_device_description()
        elif key == "Appearance" and val != 0:
            description = gatt_appearance_to_name(val)
            self.builder_object_method("appearance_label", "set_markup", f"<span size='small'>{description}</span>")
        elif key == "Percentage":
            return
            self.builder_object_method("battery_levelbar", "set_value", val)

    def builder_object_method(self, object_id, method_name, *args):
        obj = self.builder.get_object(object_id)
        method = getattr(obj, method_name, None)
        if method is None:
            raise ValueError(f"Unknown method ({method_name}) on object with id {object_id}")
        else:
            method(*args)


class BluemanListBox(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.blueman.ListBox")
        self.window: Optional[Gtk.ApplicationWindow] = None
        self.manager: Optional[Manager] = None
        self.rows: Dict[str, DeviceListBoxRow] = {}
        self.selected: Optional[str] = None
        self.builder: Gtk.Builder = Gtk.Builder.new_from_file("main_window.ui")
        self.config = Gio.Settings(schema="org.blueman.general")
        self.config.connect("changed", self.on_settings_changed)

    def do_startup(self):
        Gtk.Application.do_startup(self)

        self.manager = Manager()
        self.manager.connect_signal("device-created", self.on_device_added)
        self.manager.connect_signal("device-removed", self.on_device_removed)
        self.manager.connect_signal("battery-created", self.on_battery_added)
        # self.manager.connect_signal("battery-removed", self.on_battery_removed)

        self.listbox = self.builder.get_object("blueman_listbox")
        self.listbox.set_filter_func(self.listbox_filter)
        self.listbox.set_sort_func(self.listbox_sort)
        self.listbox.connect("row_selected", self.on_signal_selected)

        self.listbox.connect("button-press-event", self.on_clicked)
        # self.connect("drag-motion", self.drag_motion)

        search_action = Gio.SimpleAction.new_stateful("search", None, GLib.Variant.new_boolean(False))
        search_action.connect("change-state", self.on_search)
        self.add_action(search_action)

        connect_action = Gio.SimpleAction.new("connect", None)
        connect_action.connect("activate", self._on_connect)
        self.add_action(connect_action)

        pair_action = Gio.SimpleAction.new("pair", None)
        pair_action.connect("activate", self._on_connect)
        self.add_action(pair_action)

    def _on_connect(self, action, val):
        row = self.rows[self.selected]
        print(f"Connecting {row.device['Alias']}")

    def _on_pair(self, action, val):
        row = self.rows[self.selected]
        print(f"Pairing {row.device['Alias']}")

    def do_activate(self):
        if not self.window:
            self.window = self.builder.get_object("blueman_window")
            self.window.set_application(self)
            self.window.present()

            self.manager.populate_devices()
            self.on_signal_selected(self.listbox, None)

    def on_search(self, action, value):
        print(f"{action} {value}")

    def on_settings_changed(self, settings, key):
        print(settings, key)

    def drag_motion(self, widget: Gtk.Widget, _drag_context: Gdk.DragContext, _x: int, y: int, _timestamp: int) -> bool:
        row = widget.get_row_at_y(y)
        print(row)

    def on_clicked(self, widget, event):
        row = widget.get_row_at_y(event.y)
        widget.select_row(row)
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            print(widget, event, row, dir(event))
            model = Gtk.Builder.new_from_string(DEVICEMENU, -1).get_object("devicemenu")
            menu = Gtk.Popover.new_from_model(widget, model)
            menu.set_position(Gtk.PositionType.BOTTOM)
            rect = Gdk.Rectangle()
            rect.x = event.x
            rect.y = event.y
            menu.set_pointing_to(rect)
            menu.popup()

        if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            print("Double")

    def on_signal_selected(self, listbox, row):
        if row is None:
            for child in listbox:
                assert isinstance(child, Gtk.ListBoxRow)
                if child.get_selectable():
                    listbox.select_row(child)
                    break
            return

        print(f"Row selected {row.device['Alias']}")
        if self.selected is None:
            self.selected = row.object_path
            #row.reveal_detail(True)
        elif row.object_path != self.selected:
            #self.rows[self.selected].reveal_detail(False)
            self.selected = row.object_path
            #row.reveal_detail(True)

    def on_device_added(self, _manager, obj_path):
        print(f"Adding device {obj_path}")
        if obj_path not in self.rows:
            device = Device(obj_path=obj_path)
            row = DeviceListBoxRow(device, self.window.get_window(), self.window.get_scale_factor())
            self.listbox.add(row)
            row.reveal_row(True)
            self.rows[obj_path] = row

    def on_battery_added(self, _manager, obj_path):
        self.rows[obj_path].add_battery(obj_path)

    def on_device_removed(self, _manager, obj_path):
        def remove_child(container, child):
            container.remove(child)
            child.destroy()

        print(f"Removing device {obj_path}")
        row = self.rows.pop(obj_path)
        timeout = row.row_revealer.get_transition_duration() + 5
        row.reveal_row(False)
        GLib.timeout_add(timeout, remove_child, self.listbox, row)

    def listbox_filter(self, row):
        return True
        properties = row.device.get_properties()
        if "Name" not in properties:
            print(f"Hiding device {row.device['Address']}")
            return False
        else:
            return True

    def listbox_sort(self, row1, row2):
        if row1.device is None or row2.device is None:
            return 0

        row1_rank = 0
        row2_rank = 0

        if row1.device["Paired"]:
            row1_rank += 10
        if row2.device["Paired"]:
            row2_rank += 10

        if row1.device["Alias"] > row2.device["Alias"]:
            row1_rank += 1
        elif row1.device["Alias"] < row2.device["Alias"]:
            row2_rank += 1

        if row1_rank > row2_rank:
            return 1
        elif row1_rank < row2_rank:
            return -1
        else:
            return 0


app = BluemanListBox()
app.run()
