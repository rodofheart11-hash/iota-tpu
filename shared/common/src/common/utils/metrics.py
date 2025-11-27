from prometheus_client import Counter, Gauge, REGISTRY

# Keep global references so repeated imports/instantiations don't register the
# same metric name multiple times (pytest loads several services in one process).
_counter_cache: dict[str, Counter] = {}
_gauge_cache: dict[str, Gauge] = {}

label_names = ["project", "subsystem"]

# Buckets for histograms we need have higher duration than typicall web apis
COMMON_HIST_DURATION_BUKCET = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
    20.0,
    30.0,
    45.0,
    60.0,
    75.0,
    100.0,
    115.0,
    130.0,
    145.0,
    160.0,
    175.0,
    200.0,
    215.0,
    230.0,
    float("inf"),
)


def GaugeWithParams(metric_name: str, description: str) -> Gauge:
    if metric_name not in _gauge_cache:
        _gauge_cache[metric_name] = Gauge(
            metric_name,
            description,
            labelnames=label_names,
            registry=REGISTRY,
        )
    return _gauge_cache[metric_name]


def CounterWithParams(metric_name: str, description: str) -> Counter:
    if metric_name not in _counter_cache:
        _counter_cache[metric_name] = Counter(
            metric_name,
            description,
            labelnames=label_names,
            registry=REGISTRY,
        )
    return _counter_cache[metric_name]
