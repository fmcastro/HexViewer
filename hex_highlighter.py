'''
Hex Viewer
Licensed under MIT
Copyright (c) 2011 Isaac Muse <isaacmuse@gmail.com>
'''

import sublime
import sublime_plugin
from random import randrange
from hex_common import *

HIGHLIGHT_SCOPE = "string"
HIGHLIGHT_ICON = "dot"
HIGHLIGHT_STYLE = "solid"
MS_HIGHLIGHT_DELAY = 500
MAX_HIGHIGHT = 1000


class HexHighlighterListenerCommand(sublime_plugin.EventListener):
    def check_debounce(self, debounce_id):
        if self.debounce_id == debounce_id:
            sublime.active_window().run_command('hex_highlighter')
            self.debounce_id = 0

    def debounce(self):
        # Check if debunce not currently active, or if of same type,
        # but let edit override selection for undos
        debounce_id = randrange(1, 999999)
        self.debounce_id = debounce_id
        sublime.set_timeout(
            lambda: self.check_debounce(debounce_id=debounce_id),
            MS_HIGHLIGHT_DELAY
        )

    def on_selection_modified(self, view):
        self.debounce()


class HexHighlighterCommand(sublime_plugin.WindowCommand):
    def init(self):
        init_status = False
        self.address_done = False
        self.total_bytes = 0
        self.address = []
        self.selected_bytes = []

        # Get Seetings from settings file
        group_size = self.view.settings().get("hex_viewer_bits", None)
        self.inspector_enabled = hv_inspector_enable
        self.max_highlight = hv_settings.get("highlight_max_bytes", MAX_HIGHIGHT)
        self.bytes_wide = self.view.settings().get("hex_viewer_actual_bytes", None)
        self.highlight_scope = hv_settings.get("highlight_scope", HIGHLIGHT_SCOPE)
        self.highlight_icon = hv_settings.get("highlight_icon", HIGHLIGHT_ICON)
        style = hv_settings.get("highlight_style", HIGHLIGHT_STYLE)

        # No icon?
        if self.highlight_icon == "none":
            self.highlight_icon = ""

        # Process highlight style
        self.highlight_style = 0
        if style == "outline":
            self.highlight_style = sublime.DRAW_OUTLINED
        elif style == "none":
            self.highlight_style = sublime.HIDDEN
        elif style == "underline":
            self.highlight_style = sublime.DRAW_EMPTY_AS_OVERWRITE

        #Process hex grouping
        if group_size != None and self.bytes_wide != None:
            self.group_size = group_size / BITS_PER_BYTE
            init_status = True
        return init_status

    def is_enabled(self):
        return is_enabled()

    def get_address(self, start, bytes, line):
        lines = line
        align_to_address_offset = 2
        add_start = lines * self.bytes_wide + start - align_to_address_offset
        add_end = add_start + bytes - 1
        length = len(self.address)
        if length == 0:
            # Add first address group
            multi_byte = -1 if add_start == add_end else add_end
            self.address.append(add_start)
            self.address.append(multi_byte)
        elif (
            (self.address[1] == -1 and self.address[0] + 1 == add_start) or
            (self.address[1] != -1 and self.address[1] + 1 == add_start)
        ):
            # Update end address
            self.address[1] = add_end
        else:
            # Stop getting adresses if bytes are not consecutive
            self.address_done = True

    def display_address(self):
        count = ''
        if self.total_bytes == 0:
            self.view.set_status('hex_address', "Address: None")
            return
        # Display number of bytes whose address is not displayed
        if self.address_done:
            delta = 1 if self.address[1] == -1 else self.address[1] - self.address[0] + 1
            counted_bytes = self.total_bytes - delta
            if counted_bytes > 0:
                count = " [+" + str(counted_bytes) + " bytes]"
        # Display adresses
        status = "Address: "
        if self.address[1] == -1:
            status += ("0x%08x" % self.address[0]) + count
        else:
            status += ("0x%08x" % self.address[0]) + "-" + ("0x%08x" % self.address[1]) + count
        self.view.set_status('hex_address', status)

    def display_total_bytes(self):
        # Display total hex bytes
        self.view.set_status('hex_total_bytes', "Total Bytes: " + str(self.total_bytes))

    def hex_selection(self, start, bytes, first_pos):
        row, column = self.view.rowcol(first_pos)
        column = ascii_to_hex_col(column, start, self.group_size)
        hex_pos = self.view.text_point(row, column)

        # Log first byte
        if self.first_all == -1:
            self.first_all = hex_pos

         # Traverse row finding the specified bytes
        highlight_start = -1
        byte_count = bytes
        while byte_count:
            # Byte rising edge
            if self.view.score_selector(hex_pos, 'raw.nibble.upper'):
                if highlight_start == -1:
                    highlight_start = hex_pos
                hex_pos += 2
                byte_count -= 1
                # End of selection
                if byte_count == 0:
                    self.selected_bytes.append(sublime.Region(highlight_start, hex_pos))
            else:
                # Byte group falling edge
                self.selected_bytes.append(sublime.Region(highlight_start, hex_pos))
                hex_pos += 1
                highlight_start = -1
        # Log address
        if bytes and not self.address_done:
            self.get_address(start + 2, bytes, row)

    def ascii_to_hex(self, sel):
        view = self.view
        start = sel.begin()
        end = sel.end()
        bytes = 0
        ascii_range = view.extract_scope(sel.begin())

        # Determine if selection is within ascii range
        if (
                start >= ascii_range.begin() and
                (
                    # Single selection should ignore the end of line selection
                    (end == start and end < ascii_range.end() - 1) or
                    (end != start and end < ascii_range.end())
                )
            ):
            # Single char selection
            if sel.size() == 0:
                bytes = 1
                self.selected_bytes.append(sublime.Region(start, end + 1))
            else:
                # Multi char selection
                bytes = end - start
                self.selected_bytes.append(sublime.Region(start, end))
            self.total_bytes += bytes
            # Highlight hex values
            self.hex_selection(start - ascii_range.begin(), bytes, start)

    def hex_to_ascii(self, sel):
        view = self.view
        start = sel.begin()
        end = sel.end()

        # Get range of hex data
        line = view.line(start)
        hex_range = get_hex_range(line, self.group_size, self.bytes_wide)

        # Determine if selection is within hex range
        if start >= hex_range.begin() and end <= hex_range.end():
            # Adjust beginning of selection to begining of first selected byte
            start, end, bytes = adjust_hex_sel(view, start, end, self.group_size)

            # Highlight hex values and their ascii chars
            if bytes != 0:
                self.total_bytes += bytes
                # Zero based byte number
                start_byte = get_byte_count(hex_range.begin(), start + 2, self.group_size) - 1
                self.hex_selection(start_byte, bytes, start)

                # Highlight Ascii
                ascii_start = hex_range.end() + ASCII_OFFSET + start_byte
                ascii_end = ascii_start + bytes
                self.selected_bytes.append(sublime.Region(ascii_start, ascii_end))

    def get_highlights(self):
        self.first_all = -1
        for sel in self.view.sel():
            # Kick out if total bytes exceeds limit
            if self.total_bytes >= self.max_highlight:
                return

            if self.view.score_selector(sel.begin(), 'comment'):
                self.ascii_to_hex(sel)
            else:
                self.hex_to_ascii(sel)

    def run(self):
        view = self.window.active_view()
        self.view = view

        if not self.init():
            return

        self.get_highlights()

        # Show inspector panel
        if self.inspector_enabled:
            reset = False if self.total_bytes == 1 else True
            self.window.run_command(
                'hex_inspector',
                {'first_byte': self.first_all, 'reset': reset, 'bytes_wide': self.bytes_wide}
            )

        # Highlight selected regions
        if self.highlight_style == sublime.DRAW_EMPTY_AS_OVERWRITE:
            self.selected_bytes = underline(self.selected_bytes)
        view.add_regions(
            "hex_view",
            self.selected_bytes,
            self.highlight_scope,
            self.highlight_icon,
            self.highlight_style
        )
        # Display selected byte addresses and total bytes selected
        self.display_address()
        self.display_total_bytes()