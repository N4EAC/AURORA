Read AGENTS.md and create the initial Aurora v0.2 project foundation.



Build a Windows desktop application using Python and Tkinter.



Requirements:



1\. Create a clean modular project structure.

2\. Do not use the word prohibited by AGENTS.md anywhere.

3\. Preserve Aurora as the project name.

4\. Create a working GUI that opens when aurora.py is executed.

5\. Include:

&#x20;  - Message entry area

&#x20;  - Generate WAV button

&#x20;  - Decode WAV button

&#x20;  - Play button

&#x20;  - Stop button

&#x20;  - Empty waterfall panel

&#x20;  - Empty spectrum panel

&#x20;  - Status fields for Sync, CRC, Frequency Offset, SNR, and Sample Rate Error

&#x20;  - Developer Console

6\. Move the existing Aurora v0.1 modem logic into separate modem modules.

7\. Do not require SciPy. Use NumPy and the Python standard library.

8\. Add requirements.txt.

9\. Add install\_requirements.bat.

10\. Add launch\_aurora.bat.

11\. Add selftest.bat.

12\. Add automated tests for:

&#x20;   - text framing

&#x20;   - CRC

&#x20;   - FEC encode/decode

&#x20;   - WAV generation

&#x20;   - clean-channel message recovery

13\. The launch BAT file must open the GUI and must not require command-line arguments.

14\. Run all tests and fix any failures.

15\. Do not create an executable or installer yet.



Before changing files, briefly state the proposed directory structure. Then implement it.

