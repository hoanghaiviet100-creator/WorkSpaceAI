from dataclasses import dataclass
@dataclass
class GgufHeader:
    metadata: dict
@dataclass
class ElidedArray:
    length: int
    def __len__(self): return self.length
class Keys:
    class General: ARCHITECTURE='general.architecture'
    class Tokenizer: LIST='tokenizer.ggml.tokens'
    class LLM:
        BLOCK_COUNT='{arch}.block_count'
        CONTEXT_LENGTH='{arch}.context_length'
        EMBEDDING_LENGTH='{arch}.embedding_length'
        VOCAB_SIZE='{arch}.vocab_size'
        EXPERT_COUNT='{arch}.expert_count'
        FEED_FORWARD_LENGTH='{arch}.feed_forward_length'
        EXPERT_FEED_FORWARD_LENGTH='{arch}.expert_feed_forward_length'
        EXPERT_SHARED_FEED_FORWARD_LENGTH='{arch}.expert_shared_feed_forward_length'
        EXPERT_USED_COUNT='{arch}.expert_used_count'
    class Attention:
        KEY_LENGTH='{arch}.attention.key_length'
        VALUE_LENGTH='{arch}.attention.value_length'
        HEAD_COUNT='{arch}.attention.head_count'
        HEAD_COUNT_KV='{arch}.attention.head_count_kv'
        SLIDING_WINDOW='{arch}.attention.sliding_window'
        SLIDING_WINDOW_PATTERN='{arch}.attention.sliding_window_pattern'
        KEY_LENGTH_SWA='{arch}.attention.key_length_swa'
        VALUE_LENGTH_SWA='{arch}.attention.value_length_swa'
        SHARED_KV_LAYERS='{arch}.attention.shared_kv_layers'
        KV_LORA_RANK='{arch}.attention.kv_lora_rank'
        KEY_LENGTH_MLA='{arch}.attention.key_length_mla'
