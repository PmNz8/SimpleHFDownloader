# SimpleHFDownloader: Speed Up Your Hugging Face Model Downloads

This simple Python application, **SimpleHFDownloader**, uses the power of [aria2c](https://aria2.github.io/) to significantly accelerate your download speeds.

**Why use SimpleHFDownloader?**

Like many, I found that browser downloads were quite slow, often capping around 300-400 Mbps.  Aria2c is a command-line download utility known for its speed and efficiency, especially for large files. This tool provides a simple graphical interface to leverage aria2c for downloading Hugging Face models.

**Key Features:**

*   **Faster Downloads:**  Utilizes aria2c to download models much quicker than standard browser downloads, especially beneficial for large models.
*   **Easy to Use:** Just copy the Hugging Face model URL (as shown below) and paste it into the application's URL field.
*   **Multi-Part Model Support:**  Works seamlessly with models that are split into multiple parts. Simply paste the link for the *first* part of the model.
*   **Simple Interface:** Provides a basic graphical user interface for straightforward downloading.

**How to Use:**

1.  **Download and Install aria2c:**
    *   You'll need to download `aria2c.exe`. You can get it from the official [aria2 website](https://aria2.github.io/):  Look for pre-built binaries.
    *   **Important:** Place the `aria2c.exe` file inside the following folder:  `%appdata%\HFModelDownloader`.  You may need to create the `HFModelDownloader` folder inside `%appdata%` if it doesn't exist.

2.  **Run `main.py` or `main.exe` from releases:**  Execute the `main.py` script in this repository using Python.

3.  **Copy Hugging Face Model URL:**  Go to the Hugging Face model page and copy the download link.  **It's important to copy the correct link.**  It should look similar to this example (you'll find a download button or link on the model's files tab):

    ![Example of Hugging Face Download Link](https://github.com/user-attachments/assets/e108a26d-c076-4476-97ab-dc017eb993c6)

4.  **Paste URL into SimpleHFDownloader:** Paste the copied URL into the "URL" field in the SimpleHFDownloader application.

5.  **Start Download:** Click the "Start" button. The download progress will be displayed in the log window.

    ![SimpleHFDownloader Screenshot](https://github.com/user-attachments/assets/99c95e4b-f514-4482-a098-1ca060dee953)

**Important Notes:**

*   This is a very basic tool created to address a personal need for faster downloads.  It's shared in case others find it useful.
*   Make sure `aria2c.exe` is placed in the correct location (`%appdata%\HFModelDownloader`) for the application to work.
*   For multi-part models, always paste the link for the *first* part.

**Feel free to use and modify this tool as needed. If you have suggestions or improvements, contributions are welcome!**
