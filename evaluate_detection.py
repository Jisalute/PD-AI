import os
import json
import argparse
import logging
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("evaluation.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


def infer_ground_truth(filename):
    fname_lower = filename.lower()
    if 'no' in fname_lower:
        return "正常"
    elif 'p' in fname_lower:
        return "篡改"
    else:
        return None


def determine_prediction(regions, mode="strict"):
    has_tampered = any(r['detection']['result'] == "篡改" for r in regions)
    has_suspicious = any(r['detection']['result'] == "可疑" for r in regions)

    if mode == "strict":
        return "篡改" if (has_tampered or has_suspicious) else "正常"
    elif mode == "loose":
        return "篡改" if has_tampered else "正常"
    else:
        return "篡改" if has_tampered else "正常"


def calculate_metrics(y_true, y_pred):
    true_binary = [1 if t == "篡改" else 0 for t in y_true]
    pred_binary = [1 if p == "篡改" else 0 for p in y_pred]

    tp = sum(1 for t, p in zip(true_binary, pred_binary) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(true_binary, pred_binary) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(true_binary, pred_binary) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(true_binary, pred_binary) if t == 1 and p == 0)

    accuracy = (tp + tn) / len(y_true) if len(y_true) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "accuracy": accuracy, "precision": precision, "recall": recall, "f1_score": f1,
        "confusion_matrix": {"TP": tp, "TN": tn, "FP": fp, "FN": fn},
        "counts": {"total": len(y_true), "tampered": sum(1 for t in y_true if t == "篡改"),
                   "normal": sum(1 for t in y_true if t == "正常")}
    }


def generate_detailed_report(results, output_dir):
    strict_results, loose_results = [], []

    for res in results:
        strict_pred = determine_prediction(res['regions'], mode="strict")
        loose_pred = determine_prediction(res['regions'], mode="loose")

        strict_results.append(
            {'filename': res['filename'], 'ground_truth': res['ground_truth'], 'prediction': strict_pred,
             'regions': res['regions']})
        loose_results.append(
            {'filename': res['filename'], 'ground_truth': res['ground_truth'], 'prediction': loose_pred,
             'regions': res['regions']})

    y_true = [r['ground_truth'] for r in strict_results]
    y_pred_strict = [r['prediction'] for r in strict_results]
    y_pred_loose = [r['prediction'] for r in loose_results]

    metrics_strict = calculate_metrics(y_true, y_pred_strict)
    metrics_loose = calculate_metrics(y_true, y_pred_loose)

    report = {
        "evaluation_summary": {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_samples": len(results),
            "normal_samples": metrics_strict['counts']['normal'],
            "tampered_samples": metrics_strict['counts']['tampered']
        },
        "strict_mode": metrics_strict,
        "loose_mode": metrics_loose,
        "error_analysis": {
            "false_positives": [r for r in strict_results if r['ground_truth'] == "正常" and r['prediction'] == "篡改"],
            "false_negatives": [r for r in strict_results if r['ground_truth'] == "篡改" and r['prediction'] == "正常"]
        }
    }

    report_path = os.path.join(output_dir, "evaluation_report.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report, metrics_strict, metrics_loose


def main():
    parser = argparse.ArgumentParser(description="篡改检测系统准确度评估工具")
    parser.add_argument("--result_dir", type=str, default="detection_results", help="检测结果目录")
    parser.add_argument("--output_dir", type=str, default="evaluation_results", help="评估结果输出目录")
    args = parser.parse_args()

    logger.info("启动篡改检测系统准确度评估工具")

    if not os.path.exists(args.result_dir):
        logger.error(f"检测结果目录不存在: {args.result_dir}")
        return

    os.makedirs(args.output_dir, exist_ok=True)
    result_files = [f for f in os.listdir(args.result_dir) if f.endswith('_result.json')]

    if not result_files:
        logger.error("未找到有效的检测结果文件。")
        return

    evaluation_data = []

    for fname in result_files:
        base_name = fname.replace('_result.json', '')
        img_candidates = [f"{base_name}.jpg", f"{base_name}.jpeg", f"{base_name}.png"]

        matched_img = next((cand for cand in img_candidates if os.path.exists(os.path.join("images", cand))), None)

        if matched_img is None: continue

        ground_truth = infer_ground_truth(matched_img)
        if ground_truth is None: continue

        try:
            with open(os.path.join(args.result_dir, fname), 'r', encoding='utf-8') as f:
                result_data = json.load(f)
            evaluation_data.append(
                {'filename': matched_img, 'ground_truth': ground_truth, 'regions': result_data.get('regions', [])})
        except Exception as e:
            logger.error(f"解析结果文件失败 {fname}: {e}")

    if not evaluation_data:
        logger.error("无有效样本可用于评估")
        return

    logger.info(f"成功加载有效评估样本: {len(evaluation_data)} 个")
    report, metrics_strict, metrics_loose = generate_detailed_report(evaluation_data, args.output_dir)

    logger.info("评估计算完成")
    logger.info(
        f"[严格模式] 准确率: {metrics_strict['accuracy']:.2%} | 精确率: {metrics_strict['precision']:.2%} | 召回率: {metrics_strict['recall']:.2%} | F1: {metrics_strict['f1_score']:.2%}")
    logger.info(
        f"[宽松模式] 准确率: {metrics_loose['accuracy']:.2%} | 精确率: {metrics_loose['precision']:.2%} | 召回率: {metrics_loose['recall']:.2%} | F1: {metrics_loose['f1_score']:.2%}")

    fp_count = len(report['error_analysis']['false_positives'])
    fn_count = len(report['error_analysis']['false_negatives'])
    logger.info(f"错误分析: 误报 (FP) = {fp_count} 个, 漏报 (FN) = {fn_count} 个")
    logger.info(f"详细报告已输出至: {args.output_dir}")


if __name__ == "__main__":
    main()