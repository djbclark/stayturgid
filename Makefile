.PHONY: help
.DEFAULT: help

help:
	@echo "stayturgid migrated from Makefile to justfile (July 2026)"
	@echo ""
	@echo "  Install: brew install just"
	@echo "  Usage:   just --list"
	@echo "  Deploy:  just --set hosts s24 deploy"
	@echo "  Health:  just health"
	@echo "  Verify:  just --set hosts s24 verify"
	@echo "  Test:    just test"
	@echo "  Lint:    just lint"
