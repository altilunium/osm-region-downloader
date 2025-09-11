#!/usr/bin/env python3
import sys
import threading
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import time

class OSMParserThread(threading.Thread):
    def __init__(self, filepath, progress_callback=None, finished_callback=None):
        super().__init__(daemon=True)
        self.filepath = filepath
        self.progress_callback = progress_callback
        self.finished_callback = finished_callback
        self.tag_counts = Counter()
        self.values_map = defaultdict(Counter)
        self.objects_map = defaultdict(list)
        self.error = None

    def run(self):
        try:
            self._parse()
        except Exception as e:
            self.error = e
        finally:
            if self.finished_callback:
                self.finished_callback(self)

    def _parse(self):
        context = ET.iterparse(self.filepath, events=("start", "end"))
        _, root = next(context)
        last_report = time.time()
        elements_processed = 0

        for event, elem in context:
            if event == 'end' and elem.tag in ('node', 'way', 'relation'):
                elements_processed += 1
                tags = {}
                for child in elem:
                    if child.tag == 'tag':
                        k = child.attrib.get('k')
                        v = child.attrib.get('v')
                        if k is not None and v is not None:
                            tags[k] = v
                if tags:
                    obj_type = elem.tag
                    obj_id = elem.attrib.get('id') or ''
                    name = tags.get('name', None)
                    for k, v in tags.items():
                        self.tag_counts[k] += 1
                        self.values_map[k][v] += 1
                        entry_name = name if name is not None else 'unnamed key-value'
                        self.objects_map[(k, v)].append((obj_type, obj_id, entry_name))

                elem.clear()
                root.clear()
                if self.progress_callback and (time.time() - last_report) > 0.5:
                    self.progress_callback(elements_processed)
                    last_report = time.time()

        if self.progress_callback:
            self.progress_callback(elements_processed)

class OSMExplorerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('OSM Explorer')
        self.geometry('1100x700')

        self.parser_thread = None
        self.tag_counts = None
        self.values_map = None
        self.objects_map = None
        self.sort_orders = {}

        self._build_menu()
        self._build_ui()

    def _build_menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=False)
        filemenu.add_command(label='Open .osm file...', command=self.open_file)
        filemenu.add_separator()
        filemenu.add_command(label='Exit', command=self.quit)
        menubar.add_cascade(label='File', menu=filemenu)
        self.config(menu=menubar)

    def _add_tree_with_scrollbar(self, parent, columns, headings, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        for col, head, width in zip(columns, headings, widths):
            tree.heading(col, text=head, command=lambda c=col: self.sort_tree(tree, c, False))
            tree.column(col, width=width, anchor='w')
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _build_ui(self):
        top = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        top.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(top, padding=6)
        top.add(left_frame, weight=1)
        ttk.Label(left_frame, text='Tag keys (most frequent)').pack(anchor='w')
        self.keys_tree = self._add_tree_with_scrollbar(left_frame, ('key','count'), ('Key','Count'), (200,100))
        self.keys_tree.bind('<<TreeviewSelect>>', self.on_key_selected)

        mid_frame = ttk.Frame(top, padding=6)
        top.add(mid_frame, weight=1)
        ttk.Label(mid_frame, text='Values for selected key').pack(anchor='w')
        self.values_tree = self._add_tree_with_scrollbar(mid_frame, ('value','count'), ('Value','Count'), (200,100))
        self.values_tree.bind('<<TreeviewSelect>>', self.on_value_selected)

        right_frame = ttk.Frame(top, padding=6)
        top.add(right_frame, weight=2)
        ttk.Label(right_frame, text='Objects with selected key:value').pack(anchor='w')
        self.objects_tree = self._add_tree_with_scrollbar(right_frame, ('type','id','name'), ('Type','ID','Name'), (80,140,400))

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=6)
        self.copy_selected_btn = ttk.Button(btn_frame, text='Copy selected', command=self.copy_selected)
        self.copy_selected_btn.pack(side=tk.LEFT)
        self.copy_all_btn = ttk.Button(btn_frame, text='Copy all', command=self.copy_all)
        self.copy_all_btn.pack(side=tk.LEFT, padx=6)

        self.status_var = tk.StringVar(value='Ready')
        statusbar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor='w')
        statusbar.pack(fill=tk.X)

    def sort_tree(self, tree, col, reverse):
        data = [(tree.set(k, col), k) for k in tree.get_children('')]
        try:
            data.sort(key=lambda t: int(t[0]), reverse=reverse)
        except ValueError:
            data.sort(key=lambda t: t[0].lower(), reverse=reverse)
        for index, (val, k) in enumerate(data):
            tree.move(k, '', index)
        self.sort_orders[col] = not reverse

    def open_file(self):
        filepath = filedialog.askopenfilename(filetypes=[('OSM XML', '*.osm *.xml'), ('All files', '*.*')])
        if not filepath:
            return
        self.status_var.set(f'Parsing {filepath} ...')
        self._clear_all()
        self.parser_thread = OSMParserThread(filepath, progress_callback=self.on_progress, finished_callback=self.on_finished)
        self.parser_thread.start()
        self.after(200, self._poll_parser)

    def _poll_parser(self):
        if self.parser_thread is None:
            return
        if self.parser_thread.is_alive():
            self.after(200, self._poll_parser)

    def on_progress(self, count):
        self.status_var.set(f'Parsing... objects processed: {count}')

    def on_finished(self, parser):
        if parser.error:
            messagebox.showerror('Error', f'Parsing failed: {parser.error}')
            self.status_var.set('Error parsing file')
            return
        self.tag_counts = parser.tag_counts
        self.values_map = parser.values_map
        self.objects_map = parser.objects_map
        self._populate_keys()
        total_keys = len(self.tag_counts)
        total_objs = sum(self.tag_counts.values())
        self.status_var.set(f'Parsed. {total_objs} tagged objects, {total_keys} distinct tag keys.')

    def _clear_all(self):
        for t in (self.keys_tree, self.values_tree, self.objects_tree):
            for i in t.get_children():
                t.delete(i)
        self.tag_counts = None
        self.values_map = None
        self.objects_map = None

    def _populate_keys(self):
        for i in self.keys_tree.get_children():
            self.keys_tree.delete(i)
        for k, cnt in self.tag_counts.most_common():
            self.keys_tree.insert('', 'end', iid=k, values=(k, cnt))

    def on_key_selected(self, event):
        sel = self.keys_tree.selection()
        if not sel:
            return
        key = sel[0]
        for i in self.values_tree.get_children():
            self.values_tree.delete(i)
        vals = self.values_map.get(key, Counter())
        for v, cnt in vals.most_common():
            self.values_tree.insert('', 'end', iid=v, values=(v, cnt))
        self.status_var.set(f'Selected key: {key} ({len(vals)} values)')
        for i in self.objects_tree.get_children():
            self.objects_tree.delete(i)

    def on_value_selected(self, event):
        sel = self.values_tree.selection()
        if not sel:
            return
        value = sel[0]
        key_sel = self.keys_tree.selection()
        if not key_sel:
            return
        key = key_sel[0]
        objs = self.objects_map.get((key, value), [])
        for i in self.objects_tree.get_children():
            self.objects_tree.delete(i)
        for idx, (typ, oid, name) in enumerate(objs):
            self.objects_tree.insert('', 'end', iid=str(idx), values=(typ, oid, name))
        self.status_var.set(f'Selected {key}={value}: {len(objs)} objects')

    def _format_object(self, obj_tuple):
        typ, oid, name = obj_tuple
        template_type = typ.capitalize()
        safe_name = name if name else 'unnamed key-value'
        return f'* {{{{{template_type}|{oid}|{safe_name}}}}}'

    def copy_selected(self):
        sel = self.objects_tree.selection()
        if not sel:
            messagebox.showinfo('Copy selected', 'No objects selected')
            return
        lines = []
        for iid in sel:
            vals = self.objects_tree.item(iid, 'values')
            if vals:
                typ, oid, name = vals
                lines.append(self._format_object((typ, oid, name)))
        text = '\n'.join(lines)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set(f'Copied {len(lines)} objects to clipboard')

    def copy_all(self):
        all_ids = self.objects_tree.get_children()
        if not all_ids:
            messagebox.showinfo('Copy all', 'No objects to copy')
            return
        lines = []
        for iid in all_ids:
            vals = self.objects_tree.item(iid, 'values')
            if vals:
                typ, oid, name = vals
                lines.append(self._format_object((typ, oid, name)))
        text = '\n'.join(lines)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set(f'Copied {len(lines)} objects to clipboard')

if __name__ == '__main__':
    app = OSMExplorerApp()
    app.mainloop()
