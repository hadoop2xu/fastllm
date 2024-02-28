from fastllm_pytools import llm;
import ctypes;
import builtins, os, json
import numpy as np
import torch
from transformers import PreTrainedTokenizerFast
from tokenizers.decoders import ByteLevel

fastllm_data_type_dict = {
    "int4": 8,
    "int8": 3,
    "float16": 7,
    "float32": 0,
}
fastllm_weight_type_dict = {
    "linear": 1,
    "embedding": 2,
    "QuantizedLinear": 111
}

def create(model,
           tokenizer = None,
           pre_prompt = None,
           user_role = None,
           bot_role = None,
           history_sep = None,
           dtype = "float16"):
    if (dtype not in fastllm_data_type_dict):
        print("dtype should be one of ", list(fastllm_data_type_dict.keys()))
        exit(0)

    # 0.1 model info
    modelInfo = model.config.__dict__
    if model.generation_config is not None:
        modelInfo.update(model.generation_config.__dict__)
    if (pre_prompt is not None):
        modelInfo["pre_prompt"] = pre_prompt
    if (user_role is not None):
        modelInfo["user_role"] = user_role
    if (bot_role is not None):
        modelInfo["bot_role"] = bot_role
    if (history_sep):
        modelInfo["history_sep"] = history_sep
    if modelInfo["architectures"] == ["MiniCPMForCausalLM"]:
        modelInfo["model_type"] = "minicpm"
    if (modelInfo["model_type"] == "baichuan"):
        if (hasattr(model, "model") and hasattr(model.model, "get_alibi_mask")):
            # Baichuan / Baichuan2 13B
            modelInfo["use_alibi"] = "1"
        modelInfo["pre_prompt"] = ""
        if (modelInfo["vocab_size"] == 125696):
            # Baichuan 2代
            modelInfo["user_role"] = ("<FLM_FIX_TOKEN_" + str(model.generation_config.user_token_id) + ">") if hasattr(model.generation_config, "user_token_id") else "";
        else:
            # Baichuan-13B-chat
            modelInfo["user_role"] = ("<FLM_FIX_TOKEN_" + str(model.generation_config.user_token_id) + "> ") if hasattr(model.generation_config, "user_token_id") else "";
        modelInfo["bot_role"] = ("<FLM_FIX_TOKEN_" + str(model.generation_config.assistant_token_id) + ">") if hasattr(model.generation_config, "assistant_token_id") else "";
        modelInfo["history_sep"] = ""
    if (modelInfo["model_type"] == "qwen"):
        if modelInfo["chat_format"] == "chatml":
            modelInfo["im_end_id"] = tokenizer.im_end_id
            modelInfo["im_start_id"] = tokenizer.im_start_id
    if (modelInfo["model_type"] == "chatglm" and hasattr(tokenizer, "build_chat_input")):
        # chatglm3
        modelInfo["pre_prompt"] = "";
        modelInfo["user_role"] = ("<FLM_FIX_TOKEN_" + str(tokenizer.get_command("<|user|>")) + "> \n");
        modelInfo["bot_role"] = ("<FLM_FIX_TOKEN_" + str(tokenizer.get_command("<|assistant|>")) + ">");
        modelInfo["history_sep"] = "";

    if tokenizer:
        modelInfo["tokenizer_use_score"] = "1" # 分词带分数
        if len(tokenizer.all_special_tokens) > 0:
            token_set = set()
            for token in [tokenizer.bos_token, tokenizer.eos_token, tokenizer.unk_token, tokenizer.pad_token]:
                for prompt in [pre_prompt, user_role, bot_role, history_sep]:
                    if prompt and str(token) in prompt:
                        modelInfo["tokenizer_has_special_tokens"] = "1"
                token_set.add(str(token))
            if len(tokenizer.all_special_tokens) > len(token_set):
                modelInfo["tokenizer_has_special_tokens"] = "1"
        if hasattr(tokenizer, "sp_model") or (hasattr(tokenizer, "tokenizer") and hasattr(tokenizer.tokenizer, "sp_model")):
            try:
                import sentencepiece.sentencepiece_model_pb2 as model_pb2
                with open(tokenizer.vocab_file, "rb") as f:
                    sp_model_data = f.read()
                    sp_model_proto = model_pb2.ModelProto.FromString(sp_model_data)
                    modelInfo["tokenizer_add_dummy_prefix"] = sp_model_proto.normalizer_spec.add_dummy_prefix
                    modelInfo["tokenizer_remove_extra_whitespaces"] = sp_model_proto.normalizer_spec.remove_extra_whitespaces
            except:
                pass
        elif isinstance(tokenizer, PreTrainedTokenizerFast):
            if hasattr(tokenizer, "_tokenizer") and hasattr(tokenizer._tokenizer, "decoder") \
                    and isinstance(tokenizer._tokenizer.decoder, ByteLevel):
                modelInfo["tokenizer_byte_as_char"] = True

    peft_config = {}
    active_adapter = ""
    if hasattr(model, "peft_config"):
        peft_config = model.peft_config
    if hasattr(model, "active_adapter") and isinstance(model.active_adapter, str):
        # in transformers >= 4.33.0, active_adapter is a funtion in model, ignore it now
        active_adapter = model.active_adapter

    model = model.cpu();
    dict = model.state_dict()

    if (modelInfo["model_type"] == "baichuan" and modelInfo["vocab_size"] == 125696):
        # normalize lm_head for Baichuan 2
        lm_head = dict['lm_head.weight'].to(torch.float32)
        dict['lm_head.weight'] = torch.nn.functional.normalize(lm_head).to(torch.float16)
        model.load_state_dict(dict)

    model_type = modelInfo["model_type"];
    model_handle = llm.fastllm_lib.create_empty_llm_model(model_type.encode());
    for it in modelInfo.keys():
        llm.fastllm_lib.add_dict_llm_model(model_handle, str(it).encode(), str(modelInfo[it]).encode());

    for adapter_name in peft_config.keys():
        adapter_dict = peft_config[adapter_name].__dict__
        for it in adapter_dict.keys():
            llm.fastllm_lib.add_adapter_dict_llm_model(model_handle, str(adapter_name).encode(), str(it).encode(), str(adapter_dict[it]).encode())
    if len(active_adapter) != 0:
        llm.fastllm_lib.set_adapter(model_handle, str(active_adapter).encode())

    # 1. vocab
    if (tokenizer):
        if (hasattr(tokenizer, "tokenizer")):
            if modelInfo["model_type"] == "qwen":
                pass
            else:
                tokenizer = tokenizer.tokenizer
        if (hasattr(tokenizer, "sp_model")):
            piece_size = tokenizer.sp_model.piece_size()
            for i in range(piece_size):
                llm.fastllm_lib.add_tokenizer_word_llm_model(model_handle, tokenizer.sp_model.id_to_piece(i).encode(),
                                                             i, ctypes.c_float(tokenizer.sp_model.get_score(i)));
        else:
            merges = {}
            if (modelInfo["model_type"] == "moss"):
                merges = {("".join(bpe_tokens), token_index) for bpe_tokens, token_index in sorted(tokenizer.bpe_ranks.items(), key=lambda kv: kv[1])}
            elif isinstance(tokenizer, PreTrainedTokenizerFast):
                tokenizer_file = tokenizer.name_or_path + tokenizer.vocab_files_names['tokenizer_file']
                if os.path.exists(tokenizer_file):
                    with open(tokenizer_file, "r", encoding='utf-8') as f:
                        bpe_merges = json.load(f)["model"]["merges"]
                        bpe_merges = [pair.replace(" ", "") for pair in bpe_merges]
                        merges = builtins.dict(zip(bpe_merges, range(0, -len(bpe_merges), -1)))
            vocab = tokenizer.get_vocab()
            for v in vocab.keys():
                score = merges[v] if v in merges else 1.0
                if (modelInfo["model_type"] == "moss"):
                    s = [(ord(c) if c not in tokenizer.byte_decoder else tokenizer.byte_decoder[c]) for c in v]
                    llm.fastllm_lib.add_tokenizer_word_llm_model(model_handle, s, vocab[v], ctypes.c_float(score));
                elif (modelInfo["model_type"] == "qwen"):
                    llm.fastllm_lib.add_tokenizer_word_llm_model(model_handle, v, vocab[v], ctypes.c_float(1.0));
                else:
                    llm.fastllm_lib.add_tokenizer_word_llm_model(model_handle, v.encode(), vocab[v], ctypes.c_float(score));
        if ("tokenizer_has_special_tokens" in modelInfo):
            special_tokens_str = ''.join(tokenizer.all_special_tokens)
            special_tokens_len = [len(x) for x in tokenizer.all_special_tokens]
            special_tokens_ids = tokenizer.all_special_ids
            llm.fastllm_lib.set_special_tokens_llm_model(model_handle, len(special_tokens_len),
                                                         (ctypes.c_int * len(special_tokens_len))(*special_tokens_len),
                                                         special_tokens_str.encode(),
                                                         (ctypes.c_int * len(special_tokens_ids))(*special_tokens_ids));

    weight_type_dict = {}
    module_dict = {}
    weight_bits = {}
    for key, m in model.named_modules():
        if (str(type(m)).find("QuantizedLinear") != -1):
            weight_type_dict[key + ".weight"] = "QuantizedLinear";
            weight_bits[key + ".weight"] = m.weight_bit_width;
        if (isinstance(m, torch.nn.Linear)):
            weight_type_dict[key + ".weight"] = "linear"
            module_dict[key + ".weight"] = m
        if (isinstance(m, torch.nn.Embedding)):
            weight_type_dict[key] = "embedding"

    # 2. weight
    tot = 0
    for key in dict:
        ori_data_type = 0
        ori_np_data_type = np.float32
        cur_weight_type = 0
        if (key in weight_type_dict and weight_type_dict[key] in fastllm_weight_type_dict):
            cur_weight_type = fastllm_weight_type_dict[weight_type_dict[key]]
        to_data_type = 0

        if (cur_weight_type == 1):
            to_data_type = fastllm_data_type_dict[dtype]
            if (to_data_type == 7):
                ori_data_type = 7
                ori_np_data_type = np.float16
        elif (cur_weight_type == 2):
            # TODO bfloat
            to_data_type = 0

        weight_name = key
        if hasattr(model, "peft_config"):
            weight_name = weight_name.replace('base_model.model.', '')
        if (cur_weight_type == 111):
            llm.fastllm_lib.add_qlinear_weight_llm_model(model_handle, weight_name.encode(),
                                                 len(dict[key].shape),
                                                 (ctypes.c_int * len(dict[key].shape))(*list(dict[key].shape)),
                                                 weight_bits[key],
                                                 dict[key + "_scale"].numpy().astype(np.float32).ctypes.data_as(ctypes.c_void_p),
                                                 dict[key].numpy().ctypes.data_as(ctypes.c_void_p));
        else:
            llm.fastllm_lib.add_weight_llm_model(model_handle, weight_name.encode(),
                                             len(dict[key].shape),
                                             (ctypes.c_int * len(dict[key].shape))(*list(dict[key].shape)),
                                             to_data_type, cur_weight_type, ori_data_type,
                                             dict[key].numpy().astype(ori_np_data_type).ctypes.data_as(ctypes.c_void_p));
        tot += 1;
        print("convert (", tot, "/", len(dict), end = " )\r");
        dict[key].to(torch.device("meta"))

    print("");
    llm.fastllm_lib.init_params_llm_model(model_handle);
    llm.fastllm_lib.warmup_llm_model(model_handle);
    ret = llm.model("", id = model_handle);
    return ret;

