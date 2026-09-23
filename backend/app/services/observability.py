from __future__ import annotations
import os

def configure_otel(app):
    endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT','').strip()
    if not endpoint:return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        provider=TracerProvider(resource=Resource.create({'service.name':'spartan-studybuddy','deployment.environment':'local-dgx'}));provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip('/')+'/v1/traces')));trace.set_tracer_provider(provider);FastAPIInstrumentor.instrument_app(app);HTTPXClientInstrumentor().instrument();return True
    except Exception as exc:
        print(f'OpenTelemetry disabled: {exc}');return False
