import os
import json
import urllib.parse
import re
import subprocess
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import threading  # Import threading module
import queue  # Import queue for thread-safe communication
import time  # Import time for timeout


def manage_app_config(directory_path=None, sessions=None):
    """
    # Manages the application configuration in a JSON file, including the download directory and the number of sessions.
    """
    appdata_path = os.environ.get('APPDATA')
    if not appdata_path:
        appdata_path = os.path.expanduser("~")  # Fallback if APPDATA is not set
    config_file_dir = os.path.join(appdata_path, "HFModelDownloader")
    config_file_path = os.path.join(config_file_dir, "config.json")
    aria2c_path = os.path.join(config_file_dir, "aria2c.exe")  # Path to aria2c.exe

    # Check if aria2c.exe exists in the config directory
    if not os.path.exists(aria2c_path):
        # Display popup message box
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        messagebox.showerror(
            "aria2c.exe not found",
            f"aria2c.exe is not found in the application directory.\n"
            f"Please place aria2c.exe in the following directory to enable downloads:\n\n"
            f"{config_file_dir}"
        )
        root.destroy()  # Destroy the temporary root window
        return None, None  # Indicate that config loading might not be fully successful due to missing aria2c

    # Check if the directory for the configuration file exists, if not, create it
    if not os.path.exists(config_file_dir):
        os.makedirs(config_file_dir, exist_ok=True)

    # Check if the JSON configuration file exists
    if not os.path.exists(config_file_path):
        # If the file does not exist, create it with a default structure and a default number of sessions 2
        print(f"Configuration file does not exist. "
              f"Creating file: '{config_file_path}'")
        config = {
            "DIRECTORY": "",
            "SESSIONS": 2  # Default number of sessions is 2
        }
        with open(config_file_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

    # Read configuration from JSON file
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config_json = json.load(f)
    except Exception as e:
        print(f"Error reading JSON configuration file: {e}")
        return None, None  # Or handle the error in another way

    # If a new DirectoryPath is provided, update the configuration and save to file
    if directory_path is not None:
        config_json["DIRECTORY"] = directory_path

    # If a new number of sessions is provided, update the configuration and save to file
    if sessions is not None:
        config_json["SESSIONS"] = sessions

    # Save the configuration only if directory_path or sessions has been changed
    if directory_path is not None or sessions is not None:
        try:
            with open(config_file_path, 'w', encoding='utf-8') as f:
                json.dump(config_json, f, ensure_ascii=False, indent=4)
            if directory_path is not None:
                print("Download directory updated in the configuration file.")
            if sessions is not None:
                print("Number of sessions updated in the configuration file.")
        except Exception as e:
            print(f"Error writing JSON configuration file: {e}")
            return None, None  # Or handle the error in another way

    # Return the current value of DIRECTORY and SESSIONS from the configuration
    return config_json.get("DIRECTORY", ""), config_json.get("SESSIONS", 2)  # Default 2 sessions if not in config


def parse_huggingface_model_url(url):
    """
    # Parses a Hugging Face model URL to extract model information.
    """
    try:
        parsed_uri = urllib.parse.urlparse(url)
        if not parsed_uri.scheme or not parsed_uri.netloc:
            raise ValueError("Invalid URL.")
    except ValueError:
        print("Invalid URL.")
        return None

    # Get path segments, where the second segment is the author
    segments = parsed_uri.path.strip('/').split('/')
    if len(segments) < 2:
        print("URL structure is invalid.")
        return None
    author = segments[0]
    model_repo = segments[1]

    # Get the filename without extension and the extension
    file_path = parsed_uri.path
    filename_with_extension = os.path.basename(file_path)
    filename_without_extension, extension = os.path.splitext(filename_with_extension)

    # Determine the base URL for download (everything before the filename)
    base_url = url[:url.rfind('/')] if '/' in url else url

    # Pattern to detect model split into parts (e.g., -00001-of-00004)
    regex = r"^(?P<base>.+)-(?P<part>\d{5})-of-(?P<total>\d{5})$"
    match = re.match(regex, filename_without_extension)

    results = []

    if match:
        # Model is split into parts
        base_name = match.group("base")
        total_parts = int(match.group("total"))

        for i in range(1, total_parts + 1):
            part_str = str(i).zfill(5)
            new_model_name = f"{base_name}-{part_str}-of-{total_parts:05d}"  # Corrected part formatting
            download_url = f"{base_url}/{new_model_name}{extension}"
            results.append({
                "DownloadUrl": download_url,
                "Author": author,
                "ModelRepo": model_repo,
                "ModelName": new_model_name,
                "Extension": extension
            })
    else:
        # Model is in a single file
        results.append({
            "DownloadUrl": url,
            "Author": author,
            "ModelRepo": model_repo,
            "ModelName": filename_without_extension,
            "Extension": extension
        })
    return results


def download_in_thread(model_info_array, download_directory, log_queue, sessions, downloader_app_instance):
    """
    # Downloads models using aria2c in a separate thread and passes logs to the queue.
    """
    appdata_path = os.environ.get('APPDATA')
    if not appdata_path:
        appdata_path = os.path.expanduser("~")  # Fallback if APPDATA is not set
    config_file_dir = os.path.join(appdata_path, "HFModelDownloader")
    aria2c_path = os.path.join(config_file_dir, "aria2c.exe")

    if not os.path.exists(aria2c_path):
        log_queue.put("aria2c.exe not found in the configuration directory.")
        downloader_app_instance.set_downloading_state(False)  # Reset button and fields state
        return

    if not model_info_array:
        log_queue.put("No model information to download.")
        downloader_app_instance.set_downloading_state(False)  # Reset button and fields state
        return

    if not download_directory:
        log_queue.put("Destination directory has not been set.")
        downloader_app_instance.set_downloading_state(False)  # Reset button and fields state
        return

    for model in model_info_array:
        if downloader_app_instance.stop_event.is_set():  # Check stop event before starting each download
            log_queue.put("Download cancelled for: " + model['ModelName'] + " (and subsequent downloads)")
            break  # Exit loop if stop event is set

        output_path = os.path.join(download_directory, model["Author"], model["ModelRepo"])
        os.makedirs(output_path, exist_ok=True)
        output_file = f"{model['ModelName']}{model['Extension']}"

        # Building argument list
        args = [
            aria2c_path,
            "-x", str(sessions),  # Use sessions from GUI
            "-s", str(sessions),  # Use sessions from GUI
            model["DownloadUrl"],
            "--file-allocation=trunc",
            "-d", output_path,
            "-o", output_file
        ]

        log_message = f"Running aria2c for: {model['ModelName']}"
        log_queue.put(log_message)

        # Add creationflags to prevent command window on Windows
        creationflags = 0  # Default value for non-Windows platforms
        if os.name == 'nt':  # Check if running on Windows
            creationflags = subprocess.CREATE_NO_WINDOW

        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, creationflags=creationflags)
        downloader_app_instance.set_process(process)  # Store process in app instance

        while process.poll() is None:
            output = process.stdout.readline()
            if output:
                log_queue.put(output.strip())
            if downloader_app_instance.stop_event.is_set():  # Check stop event
                log_queue.put("Stop signal received. Terminating process gracefully...")
                process.terminate()  # Try to terminate gracefully
                try:
                    process.wait(timeout=5)  # Wait up to 5 seconds for termination
                except subprocess.TimeoutExpired:
                    log_queue.put("Process did not exit in time; killing it now...")
                    process.kill()  # Force kill if necessary
                break  # Exit loop after stopping
            time.sleep(0.1)  # avoid busy waiting

        if downloader_app_instance.stop_event.is_set():  # Skip logging success if stopped by user
            downloader_app_instance.stop_event.clear()  # Clear stop event after handling stop
            break  # Break out of the download loop entirely
        else:  # Log success only if not stopped by user
            if process.returncode == 0:
                log_queue.put(f"Download finished for: {model['ModelName']}")
            else:
                error_output = process.stderr.read()
                error_message = (
                    f"aria2c error during download {model['ModelName']}: "
                    f"{error_output.strip()}"
                )
                log_queue.put(error_message)

        downloader_app_instance.set_process(None)  # Clear process after download ends or is stopped

    log_queue.put("Download finished or cancelled.")
    downloader_app_instance.set_downloading_state(False)  # Ensure downloading state is set to false at the end


class DownloaderApp:
    @staticmethod
    def validate_sessions_input(new_value):
        """Validates input for the sessions field."""
        if not new_value:  # Allow empty value (for deletion)
            return True
        if not new_value.isdigit():
            return False
        if int(new_value) < 1 or int(new_value) > 9:
            return False
        return True

    def __init__(self, tk_root):
        self.tk_root = tk_root
        tk_root.title("Downloading files")
        tk_root.geometry("1000x400")  # Increased height to accommodate new row
        tk_root.resizable(True, True)
        tk_root.columnconfigure(1, weight=1)
        tk_root.rowconfigure(3, weight=1)  # rowconfigure for log_text adjusted

        self.parsed_model_info = []
        self.download_thread = None  # To hold the download thread
        self.log_queue = queue.Queue()  # Initialize log queue
        self.sessions = tk.StringVar()  # StringVar without initial value, will be set from config
        self.downloading = False  # Flag to track download state
        self.aria2c_process = None  # To store the aria2c process
        self.stop_event = threading.Event()  # Use threading.Event for stop signal

        # URL Label and Entry
        self.url_label = ttk.Label(tk_root, text="URL:")
        self.url_label.grid(row=0, column=0, padx=10, pady=5, sticky="nw")
        self.url_entry = ttk.Entry(tk_root)
        self.url_entry.grid(row=0, column=1, padx=10, pady=5, sticky="newe")
        self.url_entry.bind("<FocusOut>", self.on_url_focus_out)  # Optional: Parse on focus out as well
        self.url_entry.bind("<KeyRelease>", self.on_url_text_changed)  # Parse on text change

        # DIR Label and Entry
        self.dir_label = ttk.Label(tk_root, text="DIR:")
        self.dir_label.grid(row=1, column=0, padx=10, pady=5, sticky="nw")
        self.dir_entry = ttk.Entry(tk_root)
        self.dir_entry.grid(row=1, column=1, padx=10, pady=5, sticky="newe")
        self.dir_entry.bind("<FocusOut>", self.on_dir_lost_focus)

        # Sessions Label and Entry
        self.sessions_label = ttk.Label(tk_root, text="Sessions (1-9):")
        self.sessions_label.grid(row=2, column=0, padx=10, pady=5, sticky="nw")
        self.sessions_entry = ttk.Entry(tk_root, textvariable=self.sessions, width=5, validate="key",
                                        validatecommand=(tk_root.register(DownloaderApp.validate_sessions_input),
                                                         '%P'))  # Validation added
        self.sessions_entry.grid(row=2, column=1, padx=10, pady=5, sticky="newe")
        self.sessions_entry.bind("<FocusOut>", self.on_sessions_lost_focus)  # Bind focus out event for sessions

        # Log TextBox
        self.log_label = ttk.Label(tk_root, text="Log:")  # Added label for log
        self.log_label.grid(row=3, column=0, padx=10, pady=5, sticky="nw")
        self.log_text = tk.Text(tk_root, wrap=tk.WORD, state=tk.NORMAL, height=10)
        self.log_text.grid(row=3, column=1, padx=10, pady=5, sticky="nsew")
        self.log_text_scrollbar = ttk.Scrollbar(tk_root, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text_scrollbar.grid(row=3, column=2, sticky="ns")
        self.log_text.config(yscrollcommand=self.log_text_scrollbar.set)

        # START/STOP Button
        self.start_button = ttk.Button(tk_root, text="START", command=self.on_start_click)
        self.start_button.grid(row=4, column=0, columnspan=3, padx=10, pady=10, sticky="ew")

        # Load saved directory and sessions from config
        saved_directory, saved_sessions = manage_app_config()
        if saved_directory:
            self.dir_entry.insert(0, saved_directory)
        if saved_sessions is not None:
            self.sessions.set(str(saved_sessions))  # Set from config
        else:
            self.sessions.set("2")  # Default if not in config

        self.periodic_log_update()  # Start periodic log update

    def periodic_log_update(self):
        """Checks the log queue and updates the textbox."""
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message + '\n')
                self.log_text.see(tk.END)  # Auto scroll to the bottom
        except queue.Empty:
            pass  # No messages in queue, do nothing
        self.tk_root.after(100, self.periodic_log_update)  # Check again after 100ms

    def set_process(self, process):
        """Sets the aria2c process."""
        self.aria2c_process = process

    def set_downloading_state(self, is_downloading):
        """Changes button text and state based on download status and input fields."""
        self.downloading = is_downloading
        if self.downloading:
            self.start_button.config(text="STOP", command=self.on_stop_click, state=tk.NORMAL)  # Enable button
            self.url_entry.config(state=tk.DISABLED)  # Disable URL input
            self.dir_entry.config(state=tk.DISABLED)  # Disable DIR input
            self.sessions_entry.config(state=tk.DISABLED)  # Disable Sessions input
        else:
            self.start_button.config(text="START", command=self.on_start_click, state=tk.NORMAL)  # Enable button
            self.url_entry.config(state=tk.NORMAL)  # Enable URL input
            self.dir_entry.config(state=tk.NORMAL)  # Enable DIR input
            self.sessions_entry.config(state=tk.NORMAL)  # Enable Sessions input

    def on_dir_lost_focus(self, _event):
        """Handles the LostFocus event of the txtDir field (update after leaving the field)"""
        manage_app_config(directory_path=self.dir_entry.get())

    def on_sessions_lost_focus(self, _event):
        """Handles the LostFocus event of the txtSesje field (update after leaving the field)"""
        sessions_value = self.sessions.get()
        if sessions_value:  # Save only if there is a value
            try:
                sessions = int(sessions_value)
                manage_app_config(sessions=sessions)
            except ValueError:
                # Log error, but don't show messagebox to avoid focus issues
                print("Invalid number of sessions to save.")

    def on_url_text_changed(self, _event):
        """Handles the TextChanged event for txtUrl"""
        url_to_parse = self.url_entry.get()
        self.parse_and_display_model_info(url_to_parse)

    def on_url_focus_out(self, _event):
        """Optional: Parse URL also when focus is lost"""
        url_to_parse = self.url_entry.get()
        self.parse_and_display_model_info(url_to_parse)

    def parse_and_display_model_info(self, url_to_parse):
        """Parses URL and displays information in the log field."""
        self.parsed_model_info = parse_huggingface_model_url(url_to_parse)
        self.log_text.delete("1.0", tk.END)  # Clear log text
        if self.parsed_model_info:
            for model_info in self.parsed_model_info:
                self.log_text.insert(tk.END, f"Download URL: {model_info['DownloadUrl']}\n")
                self.log_text.insert(tk.END, f"Author: {model_info['Author']}\n")
                self.log_text.insert(tk.END, f"Model Repo: {model_info['ModelRepo']}\n")
                self.log_text.insert(tk.END, f"Model Name: {model_info['ModelName']}\n")
                self.log_text.insert(tk.END, f"Model Extension: {model_info['Extension']}\n")
                self.log_text.insert(tk.END, "-----" + '\n')
        else:
            self.log_text.insert(tk.END, "Invalid URL or unable to parse model information.\n")

    def on_start_click(self):
        """Handles the click of the START button"""
        if self.downloading:  # Prevent starting new download while one is running
            return

        download_dir = self.dir_entry.get()
        sessions_value = self.sessions.get()
        if not sessions_value:
            messagebox.showerror("Error", "Enter the number of sessions (1-9).")
            return

        try:
            sessions = int(sessions_value)
        except ValueError:
            messagebox.showerror("Error", "Invalid number of sessions.")
            return

        self.log_text.delete("1.0", tk.END)  # Clear log before new download
        self.set_downloading_state(True)  # Change button to STOP, disable inputs and set downloading flag
        self.stop_event.clear()  # Ensure stop event is clear at start of new download
        self.download_thread = threading.Thread(target=download_in_thread,
                                                args=(self.parsed_model_info, download_dir, self.log_queue,
                                                      sessions, self))  # Pass app instance
        self.download_thread.start()
        self.log_text.insert(tk.END, "Download started in the background...\n")  # Feedback to user

    def on_stop_click(self):
        """Handles the click of the STOP button"""
        if self.downloading:
            self.stop_event.set()  # Set stop event to signal stop to download thread
            self.log_queue.put("Attempting to stop current download and cancel queued downloads...")
            self.start_button.config(state=tk.DISABLED)  # Disable button during stop action
            self.url_entry.config(state=tk.DISABLED)  # Keep disabled during stop action
            self.dir_entry.config(state=tk.DISABLED)  # Keep disabled during stop action
            self.sessions_entry.config(state=tk.DISABLED)  # Keep disabled during stop action


if __name__ == "__main__":
    tk_root_window = tk.Tk()
    app = DownloaderApp(tk_root_window)
    tk_root_window.mainloop()
