from __future__ import annotations

from fastapi import Request


def repository(request: Request):
    return request.app.state.repository


def ingestion_pipeline(request: Request):
    return request.app.state.ingestion_pipeline


def task_queue(request: Request):
    return request.app.state.task_queue


def retrieval_service(request: Request):
    return request.app.state.retrieval_service


def rag_service(request: Request):
    return request.app.state.rag_service


def evaluation_service(request: Request):
    return request.app.state.evaluation_service


def ollama_client(request: Request):
    return request.app.state.ollama


def settings(request: Request):
    return request.app.state.settings

