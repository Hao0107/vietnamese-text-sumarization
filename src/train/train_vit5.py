import os
import torch
import numpy as np
import evaluate
from transformers import (
    AutoModelForSeq2SeqLM, 
    DataCollatorForSeq2Seq, 
    Seq2SeqTrainingArguments, 
    Seq2SeqTrainer
)
from dataset_loader import SummarizationDatasetLoader

# 1. Khởi tạo cấu hình và đường dẫn
MODEL_NAME = "VietAI/vit5-base-vietnews-summarization"
DATA_PATH = "../data/processed/df_processed.jsonl"
OUTPUT_DIR = "./results_vit5"

# 2. Tải Dataset và Tokenizer
loader = SummarizationDatasetLoader(model_name=MODEL_NAME)
tokenized_datasets = loader.get_ready_dataset(DATA_PATH)
tokenizer = loader.tokenizer

# 3. Tải Mô hình
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

# Chuyển mô hình sang GPU nếu có
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)

# 4. Thiết lập Metrics (ROUGE Score)
rouge_metric = evaluate.load("rouge")

def compute_metrics(eval_pred):
    predictions, labels = eval_pred
    decoded_preds = tokenizer.batch_decode(predictions, skip_special_tokens=True)
    
    # Thay thế -100 trong labels (để ignore loss) bằng pad_token
    labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
    decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)
    
    # Tính ROUGE
    result = rouge_metric.compute(
        predictions=decoded_preds, 
        references=decoded_labels, 
        use_stemmer=True
    )
    
    return {k: round(v * 100, 4) for k, v in result.items()}

# 5. Cấu hình Data Collator (Tự động padding theo batch)
data_collator = DataCollatorForSeq2Seq(tokenizer, model=model)

# 6. Thiết lập tham số huấn luyện (Tối ưu cho GPU 6GB)
training_args = Seq2SeqTrainingArguments(
    output_dir=OUTPUT_DIR,
    evaluation_strategy="epoch",      # Đánh giá sau mỗi epoch
    save_strategy="epoch",
    learning_rate=5e-5,               # Tốc độ học nhỏ để hội tụ ổn định
    per_device_train_batch_size=4,    # Batch size nhỏ cho GPU 6GB
    per_device_eval_batch_size=4,
    gradient_accumulation_steps=4,    # Tích lũy 4 bước => Batch size thực tế = 16
    weight_decay=0.01,
    save_total_limit=3,               # Chỉ giữ 3 bản backup tốt nhất để đỡ tốn ổ cứng
    num_train_epochs=10,              # Có thể tăng lên nếu loss vẫn giảm
    predict_with_generate=True,       # Bật để tính ROUGE khi eval
    fp16=True,                        # SỬ DỤNG FP16 (Mixed Precision) - QUAN TRỌNG CHO 3050
    push_to_hub=False,
    logging_dir="./logs",
    logging_steps=10,
    load_best_model_at_end=True,      # Tự động tải lại model tốt nhất sau khi train xong
)

# 7. Khởi tạo Trainer
trainer = Seq2SeqTrainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_datasets["train"],
    eval_dataset=tokenized_datasets["validation"],
    tokenizer=tokenizer,
    data_collator=data_collator,
    compute_metrics=compute_metrics,
)

# 8. Bắt đầu huấn luyện
if __name__ == "__main__":
    print(f"--- Bắt đầu huấn luyện trên thiết bị: {device} ---")
    trainer.train()
    
    # 9. Lưu mô hình cuối cùng
    trainer.save_model(os.path.join(OUTPUT_DIR, "best_model"))
    print(f"--- Huấn luyện hoàn tất! Model lưu tại: {OUTPUT_DIR}/best_model ---")