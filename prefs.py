#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
from os.path import dirname, expanduser, expandvars, exists, isdir, join, normpath
from sys import platform
import webbrowser

import Tkinter as tk
import ttk
import tkColorChooser
from ttkHyperlinkLabel import HyperlinkLabel
import myNotebook as nb

from config import applongname, config
import eddn
from hotkey import hotkeymgr
from l10n import Translations
from monitor import monitor
from theme import theme

import plug

if platform == 'darwin':
    import objc
    from Foundation import NSFileManager
    try:
        from ApplicationServices import AXIsProcessTrusted, AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
    except:
        HIServices = objc.loadBundle('HIServices', globals(), '/System/Library/Frameworks/ApplicationServices.framework/Frameworks/HIServices.framework')
        objc.loadBundleFunctions(HIServices, globals(), [('AXIsProcessTrusted', 'B'),
                                                         ('AXIsProcessTrustedWithOptions', 'B@')])
        objc.loadBundleVariables(HIServices, globals(), [('kAXTrustedCheckOptionPrompt', '@^{__CFString=}')])
    was_accessible_at_launch = AXIsProcessTrusted()

elif platform=='win32':
    # sigh tkFileDialog.askdirectory doesn't support unicode on Windows
    import ctypes
    from ctypes.wintypes import *

    SHGetLocalizedName = ctypes.windll.shell32.SHGetLocalizedName
    SHGetLocalizedName.argtypes = [LPCWSTR, LPWSTR, UINT, ctypes.POINTER(ctypes.c_int)]

    LoadString = ctypes.windll.user32.LoadStringW
    LoadString.argtypes = [HINSTANCE, UINT, LPWSTR, ctypes.c_int]

    # https://msdn.microsoft.com/en-us/library/windows/desktop/bb762115
    BIF_RETURNONLYFSDIRS   = 0x00000001
    BIF_USENEWUI           = 0x00000050
    BFFM_INITIALIZED       = 1
    BFFM_SETSELECTION      = 0x00000467
    BrowseCallbackProc = ctypes.WINFUNCTYPE(ctypes.c_int, HWND, ctypes.c_uint, LPARAM, LPARAM)

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [("hwndOwner", HWND), ("pidlRoot", LPVOID), ("pszDisplayName", LPWSTR), ("lpszTitle", LPCWSTR), ("ulFlags", UINT), ("lpfn", BrowseCallbackProc), ("lParam", LPCWSTR), ("iImage", ctypes.c_int)]

    GetParent = ctypes.windll.user32.GetParent
    GetParent.argtypes = [HWND]
    GetWindowRect = ctypes.windll.user32.GetWindowRect
    GetWindowRect.argtypes = [HWND, ctypes.POINTER(RECT)]
    CalculatePopupWindowPosition = ctypes.windll.user32.CalculatePopupWindowPosition
    CalculatePopupWindowPosition.argtypes = [ctypes.POINTER(POINT), ctypes.POINTER(SIZE), UINT, ctypes.POINTER(RECT), ctypes.POINTER(RECT)]

class PreferencesDialog(tk.Toplevel):

    def __init__(self, parent, callback):
        tk.Toplevel.__init__(self, parent)

        self.parent = parent
        self.callback = callback
        self.title(platform=='darwin' and _('Preferences') or
                   _('Settings'))

        if parent.winfo_viewable():
            self.transient(parent)

        # position over parent
        if platform!='darwin' or parent.winfo_rooty()>0:	# http://core.tcl.tk/tk/tktview/c84f660833546b1b84e7
            self.geometry("+%d+%d" % (parent.winfo_rootx(), parent.winfo_rooty()))

        # remove decoration
        if platform=='win32':
            self.attributes('-toolwindow', tk.TRUE)
        elif platform=='darwin':
            # http://wiki.tcl.tk/13428
            parent.call('tk::unsupported::MacWindowStyle', 'style', self, 'utility')
        self.resizable(tk.FALSE, tk.FALSE)

        self.cmdr = False	# Note if Cmdr changes in the Journal
        self.is_beta = False	# Note if Beta status changes in the Journal
        self.cmdrchanged_alarm = None

        frame = ttk.Frame(self)
        frame.grid(sticky=tk.NSEW)

        notebook = nb.Notebook(frame)
        notebook.bind('<<NotebookTabChanged>>', self.outvarchanged)	# Recompute on tab change

        PADX = 10
        BUTTONX = 12	# indent Checkbuttons and Radiobuttons
        PADY = 2	# close spacing

        credframe = nb.Frame(notebook)
        credframe.columnconfigure(1, weight=1)

        nb.Label(credframe, text=_('Credentials')).grid(padx=PADX, sticky=tk.W)	# Section heading in settings
        ttk.Separator(credframe, orient=tk.HORIZONTAL).grid(columnspan=2, padx=PADX, pady=PADY, sticky=tk.EW)
        self.cred_label = nb.Label(credframe)
        self.cred_label.grid(padx=PADX, columnspan=2, sticky=tk.W)
        self.cmdr_label = nb.Label(credframe, text=_('Cmdr'))	# Main window
        self.cmdr_label.grid(row=10, padx=PADX, sticky=tk.W)
        self.username_label = nb.Label(credframe, text=_('Username (Email)'))	# Use same text as E:D Launcher's login dialog
        self.username_label.grid(row=11, padx=PADX, sticky=tk.W)
        self.password_label = nb.Label(credframe, text=_('Password'))		# Use same text as E:D Launcher's login dialog
        self.password_label.grid(row=12, padx=PADX, sticky=tk.W)

        self.cmdr_text = nb.Label(credframe)
        self.cmdr_text.grid(row=10, column=1, padx=PADX, pady=PADY, sticky=tk.W)
        self.username = nb.Entry(credframe)
        self.username.grid(row=11, column=1, padx=PADX, pady=PADY, sticky=tk.EW)
        if monitor.cmdr:
            self.username.focus_set()
        self.password = nb.Entry(credframe, show=u'•')
        self.password.grid(row=12, column=1, padx=PADX, pady=PADY, sticky=tk.EW)

        nb.Label(credframe).grid(sticky=tk.W)	# big spacer
        nb.Label(credframe, text=_('Privacy')).grid(padx=PADX, sticky=tk.W)	# Section heading in settings
        ttk.Separator(credframe, orient=tk.HORIZONTAL).grid(columnspan=2, padx=PADX, pady=PADY, sticky=tk.EW)

        self.out_anon= tk.IntVar(value = config.getint('anonymous') and 1)
        nb.Label(credframe, text=_('How do you want to be identified in the saved data')).grid(columnspan=2, padx=PADX, sticky=tk.W)
        nb.Radiobutton(credframe, text=_('Cmdr name'), variable=self.out_anon, value=0).grid(columnspan=2, padx=BUTTONX, sticky=tk.W)	# Privacy setting
        nb.Radiobutton(credframe, text=_('Pseudo-anonymized ID'), variable=self.out_anon, value=1).grid(columnspan=2, padx=BUTTONX, sticky=tk.W)	# Privacy setting

        notebook.add(credframe, text=_('Identity'))		# Tab heading in settings


        outframe = nb.Frame(notebook)
        outframe.columnconfigure(0, weight=1)

        output = config.getint('output') or (config.OUT_MKT_EDDN | config.OUT_SYS_EDDN | config.OUT_SHIP)	# default settings

        self.out_label = nb.Label(outframe, text=_('Please choose what data to save'))
        self.out_label.grid(columnspan=2, padx=PADX, sticky=tk.W)
        self.out_csv = tk.IntVar(value = (output & config.OUT_MKT_CSV ) and 1)
        self.out_csv_button = nb.Checkbutton(outframe, text=_('Market data in CSV format file'), variable=self.out_csv, command=self.outvarchanged)
        self.out_csv_button.grid(columnspan=2, padx=BUTTONX, sticky=tk.W)
        self.out_td  = tk.IntVar(value = (output & config.OUT_MKT_TD  ) and 1)
        self.out_td_button = nb.Checkbutton(outframe, text=_('Market data in Trade Dangerous format file'), variable=self.out_td, command=self.outvarchanged)
        self.out_td_button.grid(columnspan=2, padx=BUTTONX, sticky=tk.W)
        self.out_ship= tk.IntVar(value = (output & (config.OUT_SHIP|config.OUT_SHIP_EDS|config.OUT_SHIP_CORIOLIS) and 1))
        self.out_ship_button = nb.Checkbutton(outframe, text=_('Ship loadout'), variable=self.out_ship, command=self.outvarchanged)	# Output setting
        self.out_ship_button.grid(columnspan=2, padx=BUTTONX, pady=(5,0), sticky=tk.W)
        self.out_auto = tk.IntVar(value = 0 if output & config.OUT_MKT_MANUAL else 1)	# inverted
        self.out_auto_button = nb.Checkbutton(outframe, text=_('Automatically update on docking'), variable=self.out_auto, command=self.outvarchanged)	# Output setting
        self.out_auto_button.grid(columnspan=2, padx=BUTTONX, pady=(5,0), sticky=tk.W)

        self.outdir = tk.StringVar()
        self.outdir.set(config.get('outdir'))
        self.outdir_label = nb.Label(outframe, text=_('File location')+':')	# Section heading in settings
        self.outdir_label.grid(padx=PADX, pady=(5,0), sticky=tk.W)
        self.outdir_entry = nb.Entry(outframe, takefocus=False)
        self.outdir_entry.grid(columnspan=2, padx=PADX, pady=(0,PADY), sticky=tk.EW)
        self.outbutton = nb.Button(outframe, text=(platform=='darwin' and _('Change...') or	# Folder selection button on OSX
                                                   _('Browse...')),	# Folder selection button on Windows
                                   command = lambda:self.filebrowse(_('File location'), self.outdir))
        self.outbutton.grid(column=1, padx=PADX, pady=PADY, sticky=tk.NSEW)
        nb.Frame(outframe).grid(pady=5)	# bottom spacer

        notebook.add(outframe, text=_('Output'))		# Tab heading in settings


        eddnframe = nb.Frame(notebook)

        HyperlinkLabel(eddnframe, text='Elite Dangerous Data Network', background=nb.Label().cget('background'), url='https://github.com/EDSM-NET/EDDN/wiki', underline=True).grid(padx=PADX, sticky=tk.W)	# Don't translate
        self.eddn_station= tk.IntVar(value = (output & config.OUT_MKT_EDDN) and 1)
        self.eddn_station_button = nb.Checkbutton(eddnframe, text=_('Send station data to the Elite Dangerous Data Network'), variable=self.eddn_station, command=self.outvarchanged)	# Output setting
        self.eddn_station_button.grid(padx=BUTTONX, pady=(5,0), sticky=tk.W)
        self.eddn_auto_button = nb.Checkbutton(eddnframe, text=_('Automatically update on docking'), variable=self.out_auto, command=self.outvarchanged)	# Output setting
        self.eddn_auto_button.grid(padx=BUTTONX, sticky=tk.W)
        self.eddn_system = tk.IntVar(value = (output & config.OUT_SYS_EDDN) and 1)
        self.eddn_system_button = nb.Checkbutton(eddnframe, text=_('Send system and scan data to the Elite Dangerous Data Network'), variable=self.eddn_system, command=self.outvarchanged)	# Output setting new in E:D 2.2
        self.eddn_system_button.grid(padx=BUTTONX, pady=(5,0), sticky=tk.W)
        self.eddn_delay= tk.IntVar(value = (output & config.OUT_SYS_DELAY) and 1)
        self.eddn_delay_button = nb.Checkbutton(eddnframe, text=_('Delay sending until docked'), variable=self.eddn_delay)	# Output setting under 'Send system and scan data to the Elite Dangerous Data Network' new in E:D 2.2
        self.eddn_delay_button.grid(padx=BUTTONX, sticky=tk.W)

        notebook.add(eddnframe, text='EDDN')		# Not translated

        # build plugin prefs tabs
        for plugin in plug.PLUGINS:
            plugframe = plugin.get_prefs(notebook, monitor.cmdr, monitor.is_beta)
            if plugframe:
                notebook.add(plugframe, text=plugin.name)

        configframe = nb.Frame(notebook)
        configframe.columnconfigure(1, weight=1)

        self.logdir = tk.StringVar()
        self.logdir.set(config.get('journaldir') or config.default_journal_dir or '')
        self.logdir_entry = nb.Entry(configframe, takefocus=False)

        if platform != 'darwin':
            # Apple's SMB implementation is way too flaky - no filesystem events and bogus NULLs
            nb.Label(configframe, text = _('E:D journal file location')+':').grid(columnspan=4, padx=PADX, sticky=tk.W)	# Location of the new Journal file in E:D 2.2
            self.logdir_entry.grid(columnspan=4, padx=PADX, pady=(0,PADY), sticky=tk.EW)
            self.logbutton = nb.Button(configframe, text=(platform=='darwin' and _('Change...') or	# Folder selection button on OSX
                                                          _('Browse...')),	# Folder selection button on Windows
                                       command = lambda:self.filebrowse(_('E:D journal file location'), self.logdir))
            self.logbutton.grid(row=10, column=3, padx=PADX, pady=PADY, sticky=tk.EW)
            if config.default_journal_dir:
                nb.Button(configframe, text=_('Default'), command=self.logdir_reset, state = config.get('journaldir') and tk.NORMAL or tk.DISABLED).grid(row=10, column=2, pady=PADY, sticky=tk.EW)	# Appearance theme and language setting

        if platform == 'win32':
            ttk.Separator(configframe, orient=tk.HORIZONTAL).grid(columnspan=4, padx=PADX, pady=PADY*4, sticky=tk.EW)

        if platform in ['darwin','win32']:
            self.hotkey_code = config.getint('hotkey_code')
            self.hotkey_mods = config.getint('hotkey_mods')
            self.hotkey_only = tk.IntVar(value = not config.getint('hotkey_always'))
            self.hotkey_play = tk.IntVar(value = not config.getint('hotkey_mute'))
            nb.Label(configframe, text = platform=='darwin' and
                     _('Keyboard shortcut') or	# Hotkey/Shortcut settings prompt on OSX
                     _('Hotkey')		# Hotkey/Shortcut settings prompt on Windows
            ).grid(row=20, padx=PADX, sticky=tk.W)
            if platform == 'darwin' and not was_accessible_at_launch:
                if AXIsProcessTrusted():
                    nb.Label(configframe, text = _('Re-start {APP} to use shortcuts').format(APP=applongname), foreground='firebrick').grid(padx=PADX, sticky=tk.W)	# Shortcut settings prompt on OSX
                else:
                    nb.Label(configframe, text = _('{APP} needs permission to use shortcuts').format(APP=applongname), foreground='firebrick').grid(columnspan=4, padx=PADX, sticky=tk.W)		# Shortcut settings prompt on OSX
                    nb.Button(configframe, text = _('Open System Preferences'), command = self.enableshortcuts).grid(padx=PADX, sticky=tk.E)		# Shortcut settings button on OSX
            else:
                self.hotkey_text = nb.Entry(configframe, width = (platform == 'darwin' and 20 or 30), justify=tk.CENTER)
                self.hotkey_text.insert(0, self.hotkey_code and hotkeymgr.display(self.hotkey_code, self.hotkey_mods) or _('None'))	# No hotkey/shortcut currently defined
                self.hotkey_text.bind('<FocusIn>', self.hotkeystart)
                self.hotkey_text.bind('<FocusOut>', self.hotkeyend)
                self.hotkey_text.grid(row=20, column=1, columnspan=2, pady=(5,0), sticky=tk.W)
                self.hotkey_only_btn = nb.Checkbutton(configframe, text=_('Only when Elite: Dangerous is the active app'), variable=self.hotkey_only, state = self.hotkey_code and tk.NORMAL or tk.DISABLED)	# Hotkey/Shortcut setting
                self.hotkey_only_btn.grid(columnspan=4, padx=PADX, pady=(5,0), sticky=tk.W)
                self.hotkey_play_btn = nb.Checkbutton(configframe, text=_('Play sound'), variable=self.hotkey_play, state = self.hotkey_code and tk.NORMAL or tk.DISABLED)	# Hotkey/Shortcut setting
                self.hotkey_play_btn.grid(columnspan=4, padx=PADX, sticky=tk.W)

        ttk.Separator(configframe, orient=tk.HORIZONTAL).grid(columnspan=4, padx=PADX, pady=PADY*4, sticky=tk.EW)
        nb.Label(configframe, text=_('Preferred websites')).grid(row=30, columnspan=4, padx=PADX, sticky=tk.W)	# Settings prompt for preferred ship loadout, system and station info websites

        self.shipyard_provider = tk.StringVar(value = config.get('shipyard_provider') in plug.provides('shipyard_url') and config.get('shipyard_provider') or 'EDSY')
        nb.Label(configframe, text=_('Shipyard')).grid(row=31, padx=PADX, pady=2*PADY, sticky=tk.W)	# Setting to decide which ship outfitting website to link to - either E:D Shipyard or Coriolis
        self.shipyard_button = nb.OptionMenu(configframe, self.shipyard_provider, self.shipyard_provider.get(), *plug.provides('shipyard_url'))
        self.shipyard_button.configure(width = 15)
        self.shipyard_button.grid(row=31, column=1, sticky=tk.W)

        self.system_provider = tk.StringVar(value = config.get('system_provider') in plug.provides('system_url') and config.get('system_provider') or 'EDSM')
        nb.Label(configframe, text=_('System')).grid(row=32, padx=PADX, pady=2*PADY, sticky=tk.W)
        self.system_button = nb.OptionMenu(configframe, self.system_provider, self.system_provider.get(), *plug.provides('system_url'))
        self.system_button.configure(width = 15)
        self.system_button.grid(row=32, column=1, sticky=tk.W)

        self.station_provider = tk.StringVar(value = config.get('station_provider') in plug.provides('station_url') and config.get('station_provider') or 'eddb')
        nb.Label(configframe, text=_('Station')).grid(row=33, padx=PADX, pady=2*PADY, sticky=tk.W)
        self.station_button = nb.OptionMenu(configframe, self.station_provider, self.station_provider.get(), *plug.provides('station_url'))
        self.station_button.configure(width = 15)
        self.station_button.grid(row=33, column=1, sticky=tk.W)

        nb.Label(configframe).grid(sticky=tk.W)	# big spacer

        notebook.add(configframe, text=_('Configuration'))	# Tab heading in settings


        self.languages = Translations.available_names()
        self.lang = tk.StringVar(value = self.languages.get(config.get('language'), _('Default')))	# Appearance theme and language setting
        self.always_ontop = tk.BooleanVar(value = config.getint('always_ontop'))
        self.theme = tk.IntVar(value = config.getint('theme'))
        self.theme_colors = [config.get('dark_text'), config.get('dark_highlight')]
        self.theme_prompts = [
            _('Normal text'),		# Dark theme color setting
            _('Highlighted text'),	# Dark theme color setting
        ]
        themeframe = nb.Frame(notebook)
        themeframe.columnconfigure(2, weight=1)
        nb.Label(themeframe, text=_('Language')).grid(row=10, padx=PADX, sticky=tk.W)	# Appearance setting prompt
        self.lang_button = nb.OptionMenu(themeframe, self.lang, self.lang.get(), *self.languages.values())
        self.lang_button.grid(row=10, column=1, columnspan=2, padx=PADX, sticky=tk.W)
        ttk.Separator(themeframe, orient=tk.HORIZONTAL).grid(columnspan=3, padx=PADX, pady=PADY*4, sticky=tk.EW)
        nb.Label(themeframe, text=_('Theme')).grid(columnspan=3, padx=PADX, sticky=tk.W)	# Appearance setting
        nb.Radiobutton(themeframe, text=_('Default'), variable=self.theme, value=0, command=self.themevarchanged).grid(columnspan=3, padx=BUTTONX, sticky=tk.W)	# Appearance theme and language setting
        nb.Radiobutton(themeframe, text=_('Dark'), variable=self.theme, value=1, command=self.themevarchanged).grid(columnspan=3, padx=BUTTONX, sticky=tk.W)	# Appearance theme setting
        if platform == 'win32':
            nb.Radiobutton(themeframe, text=_('Transparent'), variable=self.theme, value=2, command=self.themevarchanged).grid(columnspan=3, padx=BUTTONX, sticky=tk.W)	# Appearance theme setting
        self.theme_label_0 = nb.Label(themeframe, text=self.theme_prompts[0])
        self.theme_label_0.grid(row=20, padx=PADX, sticky=tk.W)
        self.theme_button_0 = nb.ColoredButton(themeframe, text=_('Station'), background='grey4', command=lambda:self.themecolorbrowse(0))	# Main window
        self.theme_button_0.grid(row=20, column=1, padx=PADX, pady=PADY, sticky=tk.NSEW)
        self.theme_label_1 = nb.Label(themeframe, text=self.theme_prompts[1])
        self.theme_label_1.grid(row=21, padx=PADX, sticky=tk.W)
        self.theme_button_1 = nb.ColoredButton(themeframe, text='  Hutton Orbital  ', background='grey4', command=lambda:self.themecolorbrowse(1))	# Do not translate
        self.theme_button_1.grid(row=21, column=1, padx=PADX, pady=PADY, sticky=tk.NSEW)
        ttk.Separator(themeframe, orient=tk.HORIZONTAL).grid(columnspan=3, padx=PADX, pady=PADY*4, sticky=tk.EW)
        self.ontop_button = nb.Checkbutton(themeframe, text=_('Always on top'), variable=self.always_ontop, command=self.themevarchanged)
        self.ontop_button.grid(columnspan=3, padx=BUTTONX, sticky=tk.W)	# Appearance setting
        nb.Label(themeframe).grid(sticky=tk.W)	# big spacer

        notebook.add(themeframe, text=_('Appearance'))	# Tab heading in settings

        # Plugin settings and info
        plugsframe = nb.Frame(notebook)
        plugsframe.columnconfigure(0, weight=1)
        plugdir = tk.StringVar()
        plugdir.set(config.plugin_dir)

        nb.Label(plugsframe, text=_('Plugins folder')+':').grid(padx=PADX, sticky=tk.W)	# Section heading in settings
        plugdirentry = nb.Entry(plugsframe, justify=tk.LEFT)
        self.displaypath(plugdir, plugdirentry)
        plugdirentry.grid(row=10, padx=PADX, sticky=tk.EW)

        nb.Button(plugsframe, text=_('Open'),	# Button that opens a folder in Explorer/Finder
                  command=lambda: webbrowser.open('file:///%s' % plugdir.get())).grid(row=10, column=1, padx=(0,PADX), sticky=tk.NSEW)

        nb.Label(plugsframe, text=_("Tip: You can disable a plugin by{CR}adding '{EXT}' to its folder name").format(EXT='.disabled')).grid(	# Help text in settings
            columnspan=2, padx=PADX, pady=10, sticky=tk.NSEW)

        enabled_plugins = [x for x in plug.PLUGINS if x.folder and x.module]
        if len(enabled_plugins):
            ttk.Separator(plugsframe, orient=tk.HORIZONTAL).grid(columnspan=3, padx=PADX, pady=PADY * 8, sticky=tk.EW)
            nb.Label(plugsframe, text=_('Enabled Plugins')+':').grid(padx=PADX, sticky=tk.W)	# List of plugins in settings
            for plugin in enabled_plugins:
                if plugin.name == plugin.folder:
                    label = nb.Label(plugsframe, text=plugin.name)
                else:
                    label = nb.Label(plugsframe, text='%s (%s)' % (plugin.folder, plugin.name))
                label.grid(columnspan=2, padx=PADX*2, sticky=tk.W)

        disabled_plugins = [x for x in plug.PLUGINS if x.folder and not x.module]
        if len(disabled_plugins):
            ttk.Separator(plugsframe, orient=tk.HORIZONTAL).grid(columnspan=3, padx=PADX, pady=PADY * 8, sticky=tk.EW)
            nb.Label(plugsframe, text=_('Disabled Plugins')+':').grid(padx=PADX, sticky=tk.W)	# List of plugins in settings
            for plugin in disabled_plugins:
                nb.Label(plugsframe, text=plugin.name).grid(columnspan=2, padx=PADX*2, sticky=tk.W)

        notebook.add(plugsframe, text=_('Plugins'))		# Tab heading in settings


        if platform=='darwin':
            self.protocol("WM_DELETE_WINDOW", self.apply)	# close button applies changes
        else:
            buttonframe = ttk.Frame(frame)
            buttonframe.grid(padx=PADX, pady=PADX, sticky=tk.NSEW)
            buttonframe.columnconfigure(0, weight=1)
            ttk.Label(buttonframe).grid(row=0, column=0)	# spacer
            button = ttk.Button(buttonframe, text=_('OK'), command=self.apply)
            button.grid(row=0, column=1, sticky=tk.E)
            button.bind("<Return>", lambda event:self.apply())
            self.protocol("WM_DELETE_WINDOW", self._destroy)

        # Selectively disable buttons depending on output settings
        self.cmdrchanged()
        self.themevarchanged()

        # disable hotkey for the duration
        hotkeymgr.unregister()

        # wait for window to appear on screen before calling grab_set
        self.parent.wm_attributes('-topmost', 0)	# needed for dialog to appear ontop of parent on OSX & Linux
        self.wait_visibility()
        self.grab_set()

        # Ensure fully on-screen
        if platform == 'win32':
            position = RECT()
            GetWindowRect(GetParent(self.winfo_id()), position)
            if CalculatePopupWindowPosition(POINT(parent.winfo_rootx(), parent.winfo_rooty()),
                                            SIZE(position.right - position.left, position.bottom - position.top),
                                            0x10000, None, position):
                self.geometry("+%d+%d" % (position.left, position.top))

    def cmdrchanged(self, event=None):
        if self.cmdr != monitor.cmdr or self.is_beta != monitor.is_beta:
            # Cmdr has changed - update settings
            if monitor.cmdr:
                self.cred_label['text'] = _('Please log in with your Elite: Dangerous account details')	# Use same text as E:D Launcher's login dialog
            else:
                self.cred_label['text'] = _('Not available while E:D is at the main menu')	# Displayed when credentials settings are greyed out

            self.cmdr_label['state'] = self.username_label['state'] = self.password_label['state'] = self.cmdr_text['state'] = self.username['state'] = self.password['state'] = monitor.cmdr and tk.NORMAL or tk.DISABLED
            self.cmdr_text['text']  = (monitor.cmdr or _('None')) + (monitor.is_beta and ' [Beta]' or '') 	# No hotkey/shortcut currently defined
            self.username['state'] = tk.NORMAL
            self.username.delete(0, tk.END)
            self.password['state'] = tk.NORMAL
            self.password.delete(0, tk.END)
            if monitor.cmdr and config.get('cmdrs') and monitor.cmdr in config.get('cmdrs'):
                config_idx = config.get('cmdrs').index(monitor.cmdr)
                self.username.insert(0, config.get('fdev_usernames')[config_idx] or '')
                self.password.insert(0, config.get_password(config.get('fdev_usernames')[config_idx]) or '')
            elif monitor.cmdr and not config.get('cmdrs') and config.get('username') and config.get('password'):
                # migration from <= 2.25
                self.username.insert(0, config.get('username') or '')
                self.password.insert(0, config.get('password') or '')
            if self.cmdr is not False:		# Don't notify on first run
                plug.notify_prefs_cmdr_changed(monitor.cmdr, monitor.is_beta)
            self.cmdr = monitor.cmdr
            self.is_beta = monitor.is_beta

        # Poll
        self.cmdrchanged_alarm = self.after(1000, self.cmdrchanged)

    def outvarchanged(self, event=None):
        self.displaypath(self.outdir, self.outdir_entry)
        self.displaypath(self.logdir, self.logdir_entry)

        logdir = self.logdir.get()
        logvalid = logdir and exists(logdir)
        if not logvalid:
            self.cred_label['text'] = 'Check %s' % _('E:D journal file location')	# Location of the new Journal file in E:D 2.2

        self.out_label['state'] = self.out_csv_button['state'] = self.out_td_button['state'] = self.out_ship_button['state'] = tk.NORMAL or tk.DISABLED
        local = self.out_td.get() or self.out_csv.get() or self.out_ship.get()
        self.out_auto_button['state']   = local and logvalid and tk.NORMAL or tk.DISABLED
        self.outdir_label['state']      = local and tk.NORMAL  or tk.DISABLED
        self.outbutton['state']         = local and tk.NORMAL  or tk.DISABLED
        self.outdir_entry['state']      = local and 'readonly' or tk.DISABLED

        self.eddn_station_button['state'] = tk.NORMAL or tk.DISABLED
        self.eddn_auto_button['state']  = self.eddn_station.get() and logvalid and tk.NORMAL or tk.DISABLED
        self.eddn_system_button['state']= logvalid and tk.NORMAL or tk.DISABLED
        self.eddn_delay_button['state'] = logvalid and eddn.replayfile and self.eddn_system.get() and tk.NORMAL or tk.DISABLED

    def filebrowse(self, title, pathvar):
        if platform != 'win32':
            import tkFileDialog
            d = tkFileDialog.askdirectory(parent=self, initialdir=expanduser(pathvar.get()), title=title, mustexist=tk.TRUE)
        else:
            def browsecallback(hwnd, uMsg, lParam, lpData):
                # set initial folder
                if uMsg==BFFM_INITIALIZED and lpData:
                    ctypes.windll.user32.SendMessageW(hwnd, BFFM_SETSELECTION, 1, lpData);
                return 0

            browseInfo = BROWSEINFO()
            browseInfo.lpszTitle = title
            browseInfo.ulFlags = BIF_RETURNONLYFSDIRS|BIF_USENEWUI
            browseInfo.lpfn = BrowseCallbackProc(browsecallback)
            browseInfo.lParam = pathvar.get().startswith('~') and join(config.home, pathvar.get()[2:]) or pathvar.get()
            ctypes.windll.ole32.CoInitialize(None)
            pidl = ctypes.windll.shell32.SHBrowseForFolderW(ctypes.byref(browseInfo))
            if pidl:
                path = ctypes.create_unicode_buffer(MAX_PATH)
                ctypes.windll.shell32.SHGetPathFromIDListW(pidl, path)
                ctypes.windll.ole32.CoTaskMemFree(pidl)
                d = path.value
            else:
                d = None

        if d:
            pathvar.set(d)
            self.outvarchanged()

    def displaypath(self, pathvar, entryfield):
        entryfield['state'] = tk.NORMAL	# must be writable to update
        entryfield.delete(0, tk.END)
        if platform=='win32':
            start = pathvar.get().lower().startswith(config.home.lower()) and len(config.home.split('\\')) or 0
            display = []
            components = normpath(pathvar.get()).split('\\')
            buf = ctypes.create_unicode_buffer(MAX_PATH)
            pidsRes = ctypes.c_int()
            for i in range(start, len(components)):
                try:
                    if (not SHGetLocalizedName('\\'.join(components[:i+1]), buf, MAX_PATH, ctypes.byref(pidsRes)) and
                        LoadString(ctypes.WinDLL(expandvars(buf.value))._handle, pidsRes.value, buf, MAX_PATH)):
                        display.append(buf.value)
                    else:
                        display.append(components[i])
                except:
                    display.append(components[i])
            entryfield.insert(0, '\\'.join(display))
        elif platform=='darwin' and NSFileManager.defaultManager().componentsToDisplayForPath_(pathvar.get()):	# None if path doesn't exist
            if pathvar.get().startswith(config.home):
                display = ['~'] + NSFileManager.defaultManager().componentsToDisplayForPath_(pathvar.get())[len(NSFileManager.defaultManager().componentsToDisplayForPath_(config.home)):]
            else:
                display = NSFileManager.defaultManager().componentsToDisplayForPath_(pathvar.get())
            entryfield.insert(0, '/'.join(display))
        else:
            if pathvar.get().startswith(config.home):
                entryfield.insert(0, '~' + pathvar.get()[len(config.home):])
            else:
                entryfield.insert(0, pathvar.get())
        entryfield['state'] = 'readonly'

    def logdir_reset(self):
        if config.default_journal_dir:
            self.logdir.set(config.default_journal_dir)
        self.outvarchanged()

    def themecolorbrowse(self, index):
        (rgb, color) = tkColorChooser.askcolor(self.theme_colors[index], title=self.theme_prompts[index], parent=self.parent)
        if color:
            self.theme_colors[index] = color
            self.themevarchanged()

    def themevarchanged(self):
        self.theme_button_0['foreground'], self.theme_button_1['foreground'] = self.theme_colors

        state = self.theme.get() and tk.NORMAL or tk.DISABLED
        self.theme_label_0['state'] = state
        self.theme_label_1['state'] = state
        self.theme_button_0['state'] = state
        self.theme_button_1['state'] = state

        if platform == 'linux2':
            # Unmanaged windows are always on top on X
            self.ontop_button['state'] = self.theme.get() and tk.DISABLED or tk.NORMAL

    def hotkeystart(self, event):
        event.widget.bind('<KeyPress>', self.hotkeylisten)
        event.widget.bind('<KeyRelease>', self.hotkeylisten)
        event.widget.delete(0, tk.END)
        hotkeymgr.acquire_start()

    def hotkeyend(self, event):
        event.widget.unbind('<KeyPress>')
        event.widget.unbind('<KeyRelease>')
        hotkeymgr.acquire_stop()	# in case focus was lost while in the middle of acquiring
        event.widget.delete(0, tk.END)
        self.hotkey_text.insert(0, self.hotkey_code and hotkeymgr.display(self.hotkey_code, self.hotkey_mods) or _('None'))	# No hotkey/shortcut currently defined

    def hotkeylisten(self, event):
        good = hotkeymgr.fromevent(event)
        if good:
            (hotkey_code, hotkey_mods) = good
            event.widget.delete(0, tk.END)
            event.widget.insert(0, hotkeymgr.display(hotkey_code, hotkey_mods))
            if hotkey_code:
                # done
                (self.hotkey_code, self.hotkey_mods) = (hotkey_code, hotkey_mods)
                self.hotkey_only_btn['state'] = tk.NORMAL
                self.hotkey_play_btn['state'] = tk.NORMAL
                self.hotkey_only_btn.focus()	# move to next widget - calls hotkeyend() implicitly
        else:
            if good is None: 	# clear
                (self.hotkey_code, self.hotkey_mods) = (0, 0)
            event.widget.delete(0, tk.END)
            if self.hotkey_code:
                event.widget.insert(0, hotkeymgr.display(self.hotkey_code, self.hotkey_mods))
                self.hotkey_only_btn['state'] = tk.NORMAL
                self.hotkey_play_btn['state'] = tk.NORMAL
            else:
                event.widget.insert(0, _('None'))	# No hotkey/shortcut currently defined
                self.hotkey_only_btn['state'] = tk.DISABLED
                self.hotkey_play_btn['state'] = tk.DISABLED
            self.hotkey_only_btn.focus()	# move to next widget - calls hotkeyend() implicitly
        return('break')	# stops further processing - insertion, Tab traversal etc


    def apply(self):
        if self.cmdr:
            if self.password.get().strip():
                config.set_password(self.username.get().strip(), self.password.get().strip())	# Can fail if keyring not unlocked
            else:
                config.delete_password(self.username.get().strip())	# user may have cleared the password field
            if not config.get('cmdrs'):
                config.set('cmdrs', [self.cmdr])
                config.set('fdev_usernames', [self.username.get().strip()])
            else:
                idx = config.get('cmdrs').index(self.cmdr) if self.cmdr in config.get('cmdrs') else -1
                _putfirst('cmdrs', idx, self.cmdr)
                _putfirst('fdev_usernames', idx, self.username.get().strip())

        config.set('output',
                   (self.out_td.get()            and config.OUT_MKT_TD) +
                   (self.out_csv.get()           and config.OUT_MKT_CSV) +
                   (config.OUT_MKT_MANUAL if not self.out_auto.get() else 0) +
                   (self.out_ship.get()          and config.OUT_SHIP) +
                   (self.eddn_station.get()      and config.OUT_MKT_EDDN) +
                   (self.eddn_system.get()       and config.OUT_SYS_EDDN) +
                   (self.eddn_delay.get()        and config.OUT_SYS_DELAY))
        config.set('outdir', self.outdir.get().startswith('~') and join(config.home, self.outdir.get()[2:]) or self.outdir.get())

        logdir = self.logdir.get()
        if config.default_journal_dir and logdir.lower() == config.default_journal_dir.lower():
            config.set('journaldir', '')	# default location
        else:
            config.set('journaldir', logdir)

        if platform in ['darwin','win32']:
            config.set('hotkey_code', self.hotkey_code)
            config.set('hotkey_mods', self.hotkey_mods)
            config.set('hotkey_always', int(not self.hotkey_only.get()))
            config.set('hotkey_mute', int(not self.hotkey_play.get()))
        config.set('shipyard_provider', self.shipyard_provider.get())
        config.set('system_provider', self.system_provider.get())
        config.set('station_provider', self.station_provider.get())

        lang_codes = { v: k for k, v in self.languages.iteritems() }	# Codes by name
        config.set('language', lang_codes.get(self.lang.get()) or '')
        Translations.install(config.get('language') or None)

        config.set('always_ontop', self.always_ontop.get())
        config.set('theme', self.theme.get())
        config.set('dark_text', self.theme_colors[0])
        config.set('dark_highlight', self.theme_colors[1])
        theme.apply(self.parent)

        config.set('anonymous', self.out_anon.get())

        # Notify
        if self.callback:
            self.callback()
        plug.notify_prefs_changed(monitor.cmdr, monitor.is_beta)

        self._destroy()

    def _destroy(self):
        if self.cmdrchanged_alarm is not None:
            self.after_cancel(self.cmdrchanged_alarm)
            self.cmdrchanged_alarm = None
        self.parent.wm_attributes('-topmost', config.getint('always_ontop') and 1 or 0)
        self.destroy()

    if platform == 'darwin':
        def enableshortcuts(self):
            self.apply()
            # popup System Preferences dialog
            try:
                # http://stackoverflow.com/questions/6652598/cocoa-button-opens-a-system-preference-page/6658201
                from ScriptingBridge import SBApplication
                sysprefs = 'com.apple.systempreferences'
                prefs = SBApplication.applicationWithBundleIdentifier_(sysprefs)
                pane = [x for x in prefs.panes() if x.id() == 'com.apple.preference.security'][0]
                prefs.setCurrentPane_(pane)
                anchor = [x for x in pane.anchors() if x.name() == 'Privacy_Accessibility'][0]
                anchor.reveal()
                prefs.activate()
            except:
                AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
            self.parent.event_generate('<<Quit>>', when="tail")


class AuthenticationDialog(tk.Toplevel):

    def __init__(self, parent, callback):
        tk.Toplevel.__init__(self, parent)

        self.parent = parent
        self.callback = callback
        self.title('Authentication')

        if parent.winfo_viewable():
            self.transient(parent)

        # position over parent
        if platform!='darwin' or parent.winfo_rooty()>0:	# http://core.tcl.tk/tk/tktview/c84f660833546b1b84e7
            self.geometry("+%d+%d" % (parent.winfo_rootx(), parent.winfo_rooty()))

        # remove decoration
        self.resizable(tk.FALSE, tk.FALSE)
        if platform=='win32':
            self.attributes('-toolwindow', tk.TRUE)
        elif platform=='darwin':
            # http://wiki.tcl.tk/13428
            parent.call('tk::unsupported::MacWindowStyle', 'style', self, 'utility')

        frame = ttk.Frame(self)
        frame.grid(sticky=tk.NSEW)
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(2, weight=1)

        ttk.Label(frame, text=_('A verification code has now been sent to the{CR}email address associated with your Elite account.') +	# Use same text as E:D Launcher's verification dialog

                  '\n' +
                  _('Please enter the code into the box below.'), anchor=tk.W, justify=tk.LEFT).grid(columnspan=4, sticky=tk.NSEW)	# Use same text as E:D Launcher's verification dialog
        ttk.Label(frame).grid(row=1, column=0)	# spacer
        self.code = ttk.Entry(frame, width=8, validate='key', validatecommand=(self.register(self.validatecode), '%P', '%d', '%i', '%S'))
        self.code.grid(row=1, column=1)
        self.code.focus_set()
        ttk.Label(frame).grid(row=1, column=2)	# spacer
        self.button = ttk.Button(frame, text=_('OK'), command=self.apply, state=tk.DISABLED)
        self.button.bind("<Return>", lambda event:self.apply())
        self.button.grid(row=1, column=3, sticky=tk.E)

        for child in frame.winfo_children():
            child.grid_configure(padx=5, pady=5)

        self.protocol("WM_DELETE_WINDOW", self._destroy)

        # wait for window to appear on screen before calling grab_set
        self.parent.wm_attributes('-topmost', 0)	# needed for dialog to appear ontop of parent on OSX & Linux
        self.wait_visibility()
        self.grab_set()

        # Ensure fully on-screen
        if platform == 'win32':
            position = RECT()
            GetWindowRect(GetParent(self.winfo_id()), position)
            if CalculatePopupWindowPosition(POINT(parent.winfo_rootx(), parent.winfo_rooty()),
                                            SIZE(position.right - position.left, position.bottom - position.top),
                                            0x10000, None, position):
                self.geometry("+%d+%d" % (position.left, position.top))

        self.bind('<Return>', self.apply)


    def validatecode(self, newval, ins, idx, diff):
        self.code.selection_clear()
        self.code.delete(0, tk.END)
        self.code.insert(0, newval.upper())
        self.code.icursor(int(idx) + (int(ins)>0 and len(diff) or 0))
        self.after_idle(lambda: self.code.config(validate='key'))	# http://tcl.tk/man/tcl8.5/TkCmd/entry.htm#M21
        self.button['state'] = len(newval.strip())==5 and tk.NORMAL or tk.DISABLED
        return True

    def apply(self, event=None):
        code = self.code.get().strip()
        if len(code) == 5:
            self.parent.wm_attributes('-topmost', config.getint('always_ontop') and 1 or 0)
            self.destroy()
            if self.callback: self.callback(code)

    def _destroy(self):
        self.parent.wm_attributes('-topmost', config.getint('always_ontop') and 1 or 0)
        self.destroy()
        if self.callback: self.callback(None)

# migration from <= 2.25. Assumes current Cmdr corresponds to the saved credentials
def migrate(current_cmdr):
    if current_cmdr and not config.get('cmdrs') and config.get('username') and config.get('password'):
        config.set_password(config.get('username'), config.get('password'))	# Can fail on Linux
        config.set('cmdrs', [current_cmdr])
        config.set('fdev_usernames', [config.get('username')])
        config.delete('username')
        config.delete('password')

# Put current Cmdr first in the lists
def make_current(current_cmdr):
    if current_cmdr and config.get('cmdrs') and current_cmdr in config.get('cmdrs'):
        idx = config.get('cmdrs').index(current_cmdr)
        _putfirst('cmdrs', idx)
        _putfirst('fdev_usernames', idx)

def _putfirst(setting, config_idx, new_value=None):
    assert config_idx>=0 or new_value is not None, (setting, config_idx, new_value)
    values = config.get(setting)
    values.insert(0, new_value if config_idx<0 else values.pop(config_idx))
    if new_value is not None:
        values[0] = new_value
    config.set(setting, values)
