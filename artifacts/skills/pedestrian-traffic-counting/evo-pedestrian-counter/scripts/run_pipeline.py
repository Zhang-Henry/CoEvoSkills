"""End-to-end pedestrian counting pipeline."""
import os, sys


def run_pipeline(video_dir, output_path, sheet_name, col_filename, col_count,
                 model_name='yolov8s.pt'):
    """
    Discover videos, count pedestrians, write Excel.
    """
    from ultralytics import YOLO
    sd = os.path.dirname(os.path.abspath(__file__))
    if sd not in sys.path:
        sys.path.insert(0, sd)
    from utils import get_video_files, count_pedestrians_in_video, write_results_to_excel
    
    videos = get_video_files(video_dir)
    if not videos:
        raise ValueError(f"No video files in {video_dir}")
    print(f"Found {len(videos)} video(s)")
    results = []
    for vp in videos:
        fn = os.path.basename(vp)
        print(f"\n{fn}")
        model = YOLO(model_name)
        n = count_pedestrians_in_video(vp, model)
        print(f"  -> {n} pedestrians")
        results.append((fn, n))
    write_results_to_excel(results, output_path, sheet_name, col_filename, col_count)
    print(f"\nWrote {output_path}")
    return results
