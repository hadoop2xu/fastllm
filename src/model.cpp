#include "utils.h"

#include "model.h"
#include "fastllm.h"
#include <sstream>

#include "chatglm.h"
#include "moss.h"
#include "llama.h"
#include "qwen.h"
#include "glm.h"

namespace fastllm {
    void basellm::LoadFromFile(const std::string &fileName) {
        this->weight.LoadFromFile(fileName);
        this->InitParams();
    }

    void basellm::InitParams() {
        if (this->weight.dicts.find("bos_token_id") != this->weight.dicts.end()) {
            if(this->weight.dicts["bos_token_id"]!="None"){
                this->bos_token_id = atoi(this->weight.dicts["bos_token_id"].c_str());
            }
            if(this->weight.dicts["eos_token_id"]!="None"){
                this->eos_token_id = atoi(this->weight.dicts["eos_token_id"].c_str());
            }
        }
        if (this->weight.dicts.find("im_start_id") != this->weight.dicts.end()) {
            this->bos_token_id = atoi(this->weight.dicts["im_start_id"].c_str());
            this->eos_token_id = atoi(this->weight.dicts["im_end_id"].c_str());
        }
        if (this->weight.dicts.find("num_hidden_layers") != this->weight.dicts.end()) {
            block_cnt = atoi(this->weight.dicts["num_hidden_layers"].c_str());
        }else if (this->weight.dicts.find("num_layers") != this->weight.dicts.end()) {
            block_cnt = atoi(this->weight.dicts["num_layers"].c_str());
        }
        if (this->weight.dicts.find("hidden_size") != this->weight.dicts.end()) {
            embed_dim = atoi(this->weight.dicts["hidden_size"].c_str());
        }
        if (this->weight.dicts.find("num_attention_heads") != this->weight.dicts.end()) {
            num_attention_heads = atoi(this->weight.dicts["num_attention_heads"].c_str());
        }
        if (this->weight.dicts.find("pre_prompt") != this->weight.dicts.end()) {
            pre_prompt = this->weight.dicts["pre_prompt"];
        }
        if (this->weight.dicts.find("user_role") != this->weight.dicts.end()) {
            user_role = this->weight.dicts["user_role"];
        }
        if (this->weight.dicts.find("bot_role") != this->weight.dicts.end()) {
            bot_role = this->weight.dicts["bot_role"];
        }
        if (this->weight.dicts.find("history_sep") != this->weight.dicts.end()) {
            history_sep = this->weight.dicts["history_sep"];
        }
        if (this->weight.dicts.find("tokenizer_add_dummy_prefix") != this->weight.dicts.end()) {
            std::string value = this->weight.dicts["tokenizer_add_dummy_prefix"];
            transform(value.begin(), value.end(), value.begin(), ::tolower);
            std::istringstream iss(value);
            iss >> std::boolalpha >> this->weight.tokenizer.addDummyPrefix;
        }
        if (this->weight.dicts.find("tokenizer_remove_extra_whitespaces") != this->weight.dicts.end()) {
            std::string value = this->weight.dicts["tokenizer_remove_extra_whitespaces"];
            transform(value.begin(), value.end(), value.begin(), ::tolower);
            std::istringstream iss(value);
            iss >> std::boolalpha >> this->weight.tokenizer.removeExtraWhitespaces;
        }
        if (this->weight.dicts.find("tokenizer_byte_as_char") != this->weight.dicts.end()) {
            std::string value = this->weight.dicts["tokenizer_byte_as_char"];
            transform(value.begin(), value.end(), value.begin(), ::tolower);
            std::istringstream iss(value);
            iss >> std::boolalpha >> this->weight.tokenizer.byteAsChar;
        }

        this->deviceMap = GetDeviceMap();
    }

    void basellm::SaveLowBitModel(const std::string &fileName, int bit) {
        this->weight.SaveLowBitModel(fileName, bit);
    }

    void basellm::SaveModel(const std::string &fileName) {
        this->weight.SaveLowBitModel(fileName, 0);
    }

    fastllm::basellm *CreateModelWithType(const std::string &modelType) {
        basellm *model = nullptr;
        if (modelType == "chatglm") {
            model = (basellm*)(new ChatGLMModel());
        } else if (modelType == "moss") {
            model = (basellm*)(new MOSSModel());
            model->weight.tokenizer.type = Tokenizer::TokenizerType::BPE;
            model->eos_token_id = 106068;
        } else if (modelType == "baichuan") {
            model = (basellm*)(new LlamaModel());
            model->model_type = "baichuan";
            model->pre_prompt = "";
            model->user_role = "<human>:";
            model->bot_role = "\n<bot>:";
            model->history_sep = "\n";
            model->weight.tokenizer.type = Tokenizer::TokenizerType::BPE;
        } else if (modelType == "internlm") {
            model = new LlamaModel();
            model->model_type = "internlm";
        } else if (modelType == "llama") {
            model = (basellm*)(new LlamaModel());
        } else if (modelType == "qwen") {
            model = (basellm *) (new QWenModel());
            model->weight.tokenizer.type = Tokenizer::TokenizerType::QWEN;
        } else if (modelType == "glm") {
            model = (basellm*)(new GLMModel());
        } else {
            ErrorInFastLLM("Unkown model type: " + modelType);
        }
        return model;
    }

    std::unique_ptr<fastllm::basellm> CreateLLMModelFromFile(const std::string &fileName) {
        std::string modelType = GetModelTypeFromFile(fileName);
        basellm *model = CreateModelWithType(modelType);
        model->LoadFromFile(fileName);
        model->WarmUp();
        return std::unique_ptr<fastllm::basellm> (model);
    }

    std::unique_ptr<basellm> CreateEmptyLLMModel(const std::string &modelType) {
        basellm *model = CreateModelWithType(modelType);
        return std::unique_ptr<fastllm::basellm> (model);
    }
}
