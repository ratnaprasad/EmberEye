"""Shared product version metadata for EmberEye development branches."""

from .core import (
	AnalyticDescriptor,
	AnalyticMetadata,
	AnalyticPlugin,
	AnalyticResult,
	FrameData,
	LicenseManager,
	LicenseSummary,
	PackageValidationResult,
	PluginManager,
	PluginRegistry,
	SensorReading,
	validate_eapkg,
)

BASE_VERSION = "2.0.0"
STUDIO_VERSION = "2.0.0"
FIELD_VERSION = "2.0.0"
SUITE_RELEASE = "2.x-dev"
BUILD_NUMBER = "20260319.2"

__version__ = BASE_VERSION

__all__ = [
	"AnalyticDescriptor",
	"AnalyticMetadata",
	"AnalyticPlugin",
	"AnalyticResult",
	"BASE_VERSION",
	"BUILD_NUMBER",
	"FIELD_VERSION",
	"FrameData",
	"LicenseManager",
	"LicenseSummary",
	"PackageValidationResult",
	"PluginManager",
	"PluginRegistry",
	"STUDIO_VERSION",
	"SUITE_RELEASE",
	"SensorReading",
	"__version__",
	"validate_eapkg",
]

