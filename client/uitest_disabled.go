//go:build !uitest

package main

import "github.com/wailsapp/wails/v2/pkg/options"

func configureUITest(_ *options.App) {}

func uiTestDataDir() string { return "" }
