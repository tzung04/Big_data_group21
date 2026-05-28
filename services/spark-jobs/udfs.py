from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StringType


def get_vi_tokenize_udf():
    """UDF tokenize tiếng Việt, fallback sang split khi underthesea không sẵn."""

    @F.udf(returnType=ArrayType(StringType()))
    def vi_tokenize(text):
        if not text:
            return []
        try:
            from underthesea import word_tokenize

            tokens = word_tokenize(text, format="list")
            stopwords = {"và", "của", "là", "có", "cho", "với", "các", "được", "trong", "này"}
            return [t.lower() for t in tokens if t not in stopwords and len(t) > 1]
        except Exception:
            return [t for t in text.lower().split() if len(t) > 1]

    return vi_tokenize
