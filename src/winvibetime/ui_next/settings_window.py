"""Settings and FirstRun windows — Apple-grade dark-mode."""

from __future__ import annotations

import sys
import tkinter as tk

import customtkinter as ctk

from . import design_tokens as T
from .components import font
from ..config import ConfigManager, DEFAULT_CONFIG
from ..models import APP_NAME
from ..system_integration import disable_startup, enable_startup, startup_enabled


def _default_ignore_config() -> dict[str, list[str]]:
    return {
        "ignore_process_names": list(DEFAULT_CONFIG["ignore_process_names"]),
        "ignore_window_title_keywords": list(DEFAULT_CONFIG["ignore_window_title_keywords"]),
        "ignore_exe_path_keywords": list(DEFAULT_CONFIG["ignore_exe_path_keywords"]),
    }


class SettingsWindow:
    def __init__(
        self,
        parent: ctk.CTk,
        config_manager: ConfigManager,
        on_save: object,
    ) -> None:
        self.parent = parent
        self.config_manager = config_manager
        self.on_save = on_save

        self.window = ctk.CTkToplevel(parent)
        self.window.title(f"{APP_NAME} 设置")
        self.window.geometry("780x720")
        self.window.minsize(600, 520)
        self.window.withdraw()
        self.window.protocol("WM_DELETE_WINDOW", self.hide)

        self.minimum_timing_var = tk.StringVar()
        self.auto_save_var = tk.StringVar()
        self.idle_timeout_var = tk.StringVar()
        self.export_directory_var = tk.StringVar()
        self.recover_unsaved_var = tk.BooleanVar(value=True)
        self.launch_on_startup_var = tk.BooleanVar(value=False)
        self.debug_tracker_var = tk.BooleanVar(value=False)

        self._build_layout()
        self.load_from_manager()

    def _build_layout(self) -> None:
        container = ctk.CTkScrollableFrame(self.window, fg_color=T.BG_PRIMARY)
        container.pack(fill="both", expand=True)

        # Header
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", padx=T.SP_XL, pady=(T.SP_XL, T.SP_LG))

        ctk.CTkLabel(
            header, text="设置",
            font=font(T.SIZE_DISPLAY, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            header, text="保存后立即生效，部分设置在下次启动时生效",
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", pady=(T.SP_XXS, 0))

        # General settings card
        card = ctk.CTkFrame(container, corner_radius=T.RADIUS_MD, fg_color=T.BG_ELEVATED)
        card.pack(fill="x", padx=T.SP_XL, pady=(0, T.SP_LG))

        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(fill="x", padx=T.SP_LG, pady=T.SP_LG)
        form.grid_columnconfigure(1, weight=1)

        self._add_entry(form, 0, "最小计时间隔 (秒)", self.minimum_timing_var)
        self._add_entry(form, 1, "自动保存间隔 (秒)", self.auto_save_var)
        self._add_entry(form, 2, "空闲暂停阈值 (秒)", self.idle_timeout_var)
        self._add_entry(form, 3, "CSV 导出目录", self.export_directory_var)

        # Toggles
        toggle_frame = ctk.CTkFrame(card, fg_color="transparent")
        toggle_frame.pack(fill="x", padx=T.SP_LG, pady=(0, T.SP_LG))

        ctk.CTkSwitch(
            toggle_frame, text="启动时恢复未保存数据",
            variable=self.recover_unsaved_var,
            font=font(T.SIZE_BODY),
        ).pack(anchor="w", pady=(0, T.SP_SM))

        self.startup_switch = ctk.CTkSwitch(
            toggle_frame, text="开机自动启动",
            variable=self.launch_on_startup_var,
            font=font(T.SIZE_BODY),
        )
        self.startup_switch.pack(anchor="w", pady=(0, T.SP_SM))

        if sys.platform != "win32":
            self.startup_switch.configure(state="disabled")

        ctk.CTkSwitch(
            toggle_frame, text="调试模式",
            variable=self.debug_tracker_var,
            font=font(T.SIZE_BODY),
        ).pack(anchor="w")

        # Ignore rules card
        ignore_card = ctk.CTkFrame(container, corner_radius=T.RADIUS_MD, fg_color=T.BG_ELEVATED)
        ignore_card.pack(fill="both", expand=True, padx=T.SP_XL, pady=(0, T.SP_LG))

        ctk.CTkLabel(
            ignore_card, text="忽略规则",
            font=font(T.SIZE_HEADLINE, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="w",
        ).pack(fill="x", padx=T.SP_LG, pady=(T.SP_LG, T.SP_SM))

        lists_frame = ctk.CTkFrame(ignore_card, fg_color="transparent")
        lists_frame.pack(fill="both", expand=True, padx=T.SP_LG, pady=(0, T.SP_LG))
        for col in range(3):
            lists_frame.grid_columnconfigure(col, weight=1)
        lists_frame.grid_rowconfigure(0, weight=1)

        self.process_text = self._add_text_col(lists_frame, 0, "忽略进程名", "每行一个")
        self.title_text = self._add_text_col(lists_frame, 1, "忽略标题关键字", "每行一个")
        self.path_text = self._add_text_col(lists_frame, 2, "忽略路径关键字", "每行一个")

        # Action buttons
        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.pack(fill="x", padx=T.SP_XL, pady=(0, T.SP_XL))

        ctk.CTkButton(
            actions, text="重新加载",
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_SECONDARY,
            font=font(T.SIZE_BODY),
            corner_radius=T.RADIUS_SM,
            width=100, height=36,
            command=self.load_from_manager,
        ).pack(side="left")

        ctk.CTkButton(
            actions, text="保存",
            font=font(T.SIZE_BODY),
            corner_radius=T.RADIUS_SM,
            width=100, height=36,
            command=self.save_and_apply,
        ).pack(side="right")

        ctk.CTkButton(
            actions, text="关闭",
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_SECONDARY,
            font=font(T.SIZE_BODY),
            corner_radius=T.RADIUS_SM,
            width=80, height=36,
            command=self.hide,
        ).pack(side="right", padx=(0, T.SP_SM))

    def _add_entry(self, parent: ctk.CTkFrame, row: int, label: str, var: tk.StringVar) -> None:
        ctk.CTkLabel(
            parent, text=label,
            font=font(T.SIZE_BODY),
            text_color=T.TEXT_PRIMARY, anchor="w",
        ).grid(row=row, column=0, sticky="w", pady=T.SP_XS, padx=(0, T.SP_MD))

        ctk.CTkEntry(
            parent, textvariable=var,
            height=32, font=font(T.SIZE_BODY),
            corner_radius=T.RADIUS_SM,
        ).grid(row=row, column=1, sticky="ew", pady=T.SP_XS)

    def _add_text_col(self, parent: ctk.CTkFrame, col: int, title: str, hint: str) -> ctk.CTkTextbox:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else T.SP_SM, 0))

        ctk.CTkLabel(
            frame, text=title,
            font=font(T.SIZE_CAPTION, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            frame, text=hint,
            font=font(T.SIZE_MICRO),
            text_color=T.TEXT_TERTIARY, anchor="w",
        ).pack(fill="x", pady=(0, T.SP_XXS))

        textbox = ctk.CTkTextbox(
            frame, height=180,
            font=font(T.SIZE_CAPTION),
            corner_radius=T.RADIUS_SM,
        )
        textbox.pack(fill="both", expand=True)
        return textbox

    def _set_textbox(self, widget: ctk.CTkTextbox, lines: list[str]) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", "\n".join(lines))

    def _get_textbox_lines(self, widget: ctk.CTkTextbox) -> list[str]:
        return [line.strip() for line in widget.get("1.0", "end").splitlines() if line.strip()]

    def load_from_manager(self) -> None:
        self.config_manager.reload()
        self.minimum_timing_var.set(str(self.config_manager.minimum_timing_seconds()))
        self.auto_save_var.set(str(self.config_manager.auto_save_seconds()))
        self.idle_timeout_var.set(str(self.config_manager.idle_timeout_seconds()))
        self.export_directory_var.set(self.config_manager.export_directory_raw())
        self.recover_unsaved_var.set(self.config_manager.recover_unsaved_on_startup())

        launch = self.config_manager.launch_on_startup()
        if sys.platform == "win32":
            try:
                launch = startup_enabled()
            except Exception:
                pass
        self.launch_on_startup_var.set(launch)
        self.debug_tracker_var.set(self.config_manager.debug_tracker())
        self._set_textbox(self.process_text, sorted(self.config_manager.get_list("ignore_process_names")))
        self._set_textbox(self.title_text, self.config_manager.get_list("ignore_window_title_keywords"))
        self._set_textbox(self.path_text, self.config_manager.get_list("ignore_exe_path_keywords"))

    def save_and_apply(self) -> None:
        from tkinter import messagebox
        try:
            minimum_timing = max(0.2, float(self.minimum_timing_var.get().strip()))
            auto_save = max(5, int(self.auto_save_var.get().strip()))
            idle_timeout = max(10, int(self.idle_timeout_var.get().strip()))
        except ValueError:
            messagebox.showerror(APP_NAME, "数值格式不正确，请检查输入", parent=self.window)
            return

        updates = {
            "minimum_timing_seconds": minimum_timing,
            "auto_save_seconds": auto_save,
            "idle_timeout_seconds": idle_timeout,
            "recover_unsaved_on_startup": bool(self.recover_unsaved_var.get()),
            "launch_on_startup": bool(self.launch_on_startup_var.get()),
            "debug_tracker": bool(self.debug_tracker_var.get()),
            "export_directory": self.export_directory_var.get().strip() or "exports",
            "ignore_process_names": self._get_textbox_lines(self.process_text),
            "ignore_window_title_keywords": self._get_textbox_lines(self.title_text),
            "ignore_exe_path_keywords": self._get_textbox_lines(self.path_text),
        }

        try:
            self.on_save(updates)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"保存失败：\n{exc}", parent=self.window)
            return

        messagebox.showinfo(APP_NAME, "设置已保存", parent=self.window)
        self.hide()

    def show(self) -> None:
        self.load_from_manager()
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def hide(self) -> None:
        self.window.withdraw()


class FirstRunWindow:
    def __init__(
        self,
        parent: ctk.CTk,
        config_manager: ConfigManager,
        on_apply: object,
        on_skip: object,
        notify: object,
    ) -> None:
        self.parent = parent
        self.config_manager = config_manager
        self.on_apply = on_apply
        self.on_skip = on_skip
        self.notify = notify

        self.window = ctk.CTkToplevel(parent)
        self.window.title(f"欢迎使用 {APP_NAME}")
        self.window.geometry("520x400")
        self.window.minsize(440, 360)
        self.window.withdraw()
        self.window.protocol("WM_DELETE_WINDOW", self.skip)

        self.launch_on_startup_var = tk.BooleanVar(value=False)
        self.debug_tracker_var = tk.BooleanVar(value=False)
        self.keep_default_ignore_var = tk.BooleanVar(value=True)

        self._build_layout()
        self.load_defaults()

    def _build_layout(self) -> None:
        container = ctk.CTkFrame(self.window, fg_color=T.BG_PRIMARY, corner_radius=0)
        container.pack(fill="both", expand=True)

        # Card
        card = ctk.CTkFrame(container, corner_radius=T.RADIUS_LG, fg_color=T.BG_ELEVATED)
        card.pack(fill="both", expand=True, padx=T.SP_XL, pady=T.SP_XL)

        ctk.CTkLabel(
            card, text="欢迎使用 WinVibeTime",
            font=font(T.SIZE_TITLE, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="w",
        ).pack(fill="x", padx=T.SP_LG, pady=(T.SP_LG, T.SP_XS))

        ctk.CTkLabel(
            card, text="选择你的偏好，之后可随时在托盘菜单中修改",
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=T.SP_LG, pady=(0, T.SP_LG))

        # Options
        options = ctk.CTkFrame(card, fg_color="transparent")
        options.pack(fill="x", padx=T.SP_LG)

        self.startup_switch = ctk.CTkSwitch(
            options, text="开机自动启动",
            variable=self.launch_on_startup_var,
            font=font(T.SIZE_BODY),
        )
        self.startup_switch.pack(anchor="w", pady=(0, T.SP_SM))

        if sys.platform != "win32":
            self.startup_switch.configure(state="disabled")

        ctk.CTkSwitch(
            options, text="调试模式",
            variable=self.debug_tracker_var,
            font=font(T.SIZE_BODY),
        ).pack(anchor="w", pady=(0, T.SP_SM))

        ctk.CTkSwitch(
            options, text="保留默认忽略列表",
            variable=self.keep_default_ignore_var,
            font=font(T.SIZE_BODY),
        ).pack(anchor="w")

        # Hint
        hint_frame = ctk.CTkFrame(card, corner_radius=T.RADIUS_SM, fg_color=T.BG_HOVER)
        hint_frame.pack(fill="x", padx=T.SP_LG, pady=T.SP_LG)

        ctk.CTkLabel(
            hint_frame,
            text="默认忽略列表会排除系统窗口，让统计更清晰",
            font=font(T.SIZE_MICRO),
            text_color=T.TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=T.SP_MD, pady=T.SP_SM)

        # Actions
        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.pack(fill="x", padx=T.SP_XL, pady=(0, T.SP_LG))

        ctk.CTkButton(
            actions, text="稍后设置",
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_SECONDARY,
            font=font(T.SIZE_BODY),
            corner_radius=T.RADIUS_SM,
            width=100, height=36,
            command=self.skip,
        ).pack(side="left")

        ctk.CTkButton(
            actions, text="开始使用",
            font=font(T.SIZE_BODY),
            corner_radius=T.RADIUS_SM,
            width=120, height=36,
            command=self.apply,
        ).pack(side="right")

    def load_defaults(self) -> None:
        self.config_manager.reload()
        launch = self.config_manager.launch_on_startup()
        if sys.platform == "win32":
            try:
                launch = startup_enabled()
            except Exception:
                pass

        current_ignore = _default_ignore_config()
        keep = all(
            self.config_manager.get_list(key) == current_ignore[key]
            for key in current_ignore
        )

        self.launch_on_startup_var.set(launch)
        self.debug_tracker_var.set(self.config_manager.debug_tracker())
        self.keep_default_ignore_var.set(keep)

    def show(self) -> None:
        self.load_defaults()
        self.window.deiconify()
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.lift()
        self.window.focus_force()

    def hide(self) -> None:
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.withdraw()

    def apply(self) -> None:
        from tkinter import messagebox
        updates: dict[str, object] = {
            "first_run_completed": True,
            "launch_on_startup": bool(self.launch_on_startup_var.get()),
            "debug_tracker": bool(self.debug_tracker_var.get()),
        }

        if self.keep_default_ignore_var.get():
            updates.update(_default_ignore_config())
        else:
            updates.update({
                "ignore_process_names": [],
                "ignore_window_title_keywords": [],
                "ignore_exe_path_keywords": [],
            })

        try:
            self.on_apply(updates)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"设置失败：\n{exc}", parent=self.window)
            return

        self.hide()
        self.notify(APP_NAME, "偏好已保存，可随时在设置中修改")

    def skip(self) -> None:
        from tkinter import messagebox
        try:
            self.on_skip({"first_run_completed": True})
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"保存失败：\n{exc}", parent=self.window)
            return
        self.hide()
        self.notify(APP_NAME, "已跳过引导，可稍后在设置中修改")
