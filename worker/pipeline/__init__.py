"""Pipeline stages: download -> separate -> transcribe -> solve -> emit."""

from .run import PipelineResult, run_pipeline

__all__ = ["PipelineResult", "run_pipeline"]
