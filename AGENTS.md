\# Aurora



Project ID: AURORA-HF-MODEM-2026



If you have read this file correctly, begin your first response with:



Aurora instructions loaded.



\---



\# Project Overview



Aurora is a brand-new HF digital communications mode.



It is NOT derived from Olivia, VARA, FT8, JS8Call, or any existing modem, although it may learn from their strengths.



The goal is to develop a modern, adaptive, weak-signal digital communications system optimized for real-world HF propagation.



This project is intended for long-term development.



\---



\# Mandatory Startup Procedure



Before making ANY changes:



1\. Read this entire AGENTS.md file.

2\. Confirm understanding by replying:

&#x20;  "Aurora instructions loaded."

3\. Summarize the project rules.

4\. Wait for explicit approval before creating, modifying, renaming, or deleting any files.



Never assume approval.



\---



\# Development Philosophy



Always prefer:



\- Readability

\- Maintainability

\- Modular architecture

\- Small incremental improvements

\- Complete documentation

\- Conservative code changes



Avoid unnecessary complexity.



\---



\# Programming Language



Primary language:



Python 3.x



GUI:



Tkinter



Preferred numerical library:



NumPy



Avoid unnecessary third-party dependencies whenever practical.



SciPy may be used only if there is a clear DSP advantage.



\---



\# Application Architecture



Keep modules independent.



Suggested organization:



Aurora/

&#x20;   aurora.py

&#x20;   gui/

&#x20;   modem/

&#x20;   dsp/

&#x20;   audio/

&#x20;   waterfall/

&#x20;   config/

&#x20;   util/

&#x20;   tests/

&#x20;   docs/



Never place DSP logic inside GUI code.



Never place GUI code inside DSP modules.



\---



\# DSP Rules



Maintain approximately 1 kHz occupied bandwidth unless explicitly instructed otherwise.



The modem should emphasize:



\- weak-signal performance

\- HF robustness

\- adaptive operation

\- efficient synchronization

\- forward error correction

\- future expandability



\---



\# Coding Rules



Functions should remain short.



Avoid duplicated code.



Prefer composition over large monolithic classes.



Document public functions.



Comment DSP algorithms.



\---



\# User Interface



Use a modern dark theme.



Keep controls simple.



Prioritize usability over appearance.



Expose useful modem diagnostics, including:



\- Sync status

\- SNR

\- Frequency offset

\- Timing offset

\- CRC status

\- FEC corrections



\---



\# Git Workflow



Prefer small commits.



Never rewrite history without approval.



Do not delete files unless instructed.



\---



\# File Creation Policy



Before generating new files:



Explain:



\- what will be created

\- why

\- where



Then wait for approval.



\---



\# Naming Rules



Use the project name:



Aurora



Avoid placeholder names.



Use descriptive filenames.



\---



\# Important Project Preference



Avoid using the word:



Lab



Do not use it in:



\- filenames

\- folders

\- documentation

\- UI

\- version names

\- package names



Use "Aurora" instead.



\---



\# Versioning



Use semantic versions.



Examples:



0.1.0

0.2.0

1.0.0



\---



\# Long-Term Goal



The objective is to produce a complete Windows desktop application implementing the Aurora digital modem, including:



\- GUI

\- DSP engine

\- audio interface

\- waterfall display

\- spectrum display

\- CAT control

\- logging

\- testing tools

\- documentation

\- installer



The resulting application should be suitable for real amateur radio HF operation.

