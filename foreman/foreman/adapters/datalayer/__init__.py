try:
    from .datalayer import DatalayerAdapter
    AVAILABLE = True
except ImportError:
    DatalayerAdapter = None
    AVAILABLE = False