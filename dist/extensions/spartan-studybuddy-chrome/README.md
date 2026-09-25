# Spartan StudyBuddy Chrome extension

Manifest V3 companion for enterprise learning/onboarding. It tracks opt-in learning activity, YouTube progress, research-paper/web engagement and text selections, and synchronizes those events with the central StudyBuddy memory on the DGX Spark.

## Install

Run `make extensions-package`, unzip `dist/extensions/spartan-studybuddy-chrome.zip`, then use Chrome → Extensions → Developer mode → Load unpacked.

Set the Spark API URL, project ID and user ID in the popup. No source changes are required.
