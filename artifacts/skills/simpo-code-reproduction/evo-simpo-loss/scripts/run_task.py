"""End-to-end entry point for SimPO loss task.

This script:
1. Installs required packages if missing
2. Injects the simpo_loss implementation into the trainer file
3. Runs the unit test to generate loss output
4. Logs Python version and packages
5. Validates the output
"""
import subprocess
import sys
import os


def ensure_packages():
    """Install required packages if not present."""
    required = ['torch', 'transformers', 'trl', 'accelerate', 'datasets', 'peft', 'rich', 'numpy']
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        # Use specific versions known to work
        version_map = {
            'torch': 'torch==2.2.2',
            'transformers': 'transformers==4.44.2',
            'trl': 'trl==0.9.6',
            'accelerate': 'accelerate==0.29.2',
            'datasets': 'datasets',
            'peft': 'peft==0.7.1',
            'rich': 'rich',
            'numpy': 'numpy==1.26.4',
        }
        install_list = [version_map.get(p, p) for p in missing]
        subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + install_list)


def run_simpo_task(
    project_dir: str = '/root/SimPO',
    output_path: str = '/root/loss.npz',
    python_info_path: str = '/root/python_info.txt',
):
    """Run the complete SimPO loss task.

    Args:
        project_dir: Path to the SimPO project directory.
        output_path: Path where loss.npz will be saved.
        python_info_path: Path where Python version info will be saved.
    """
    # Step 1: Ensure packages
    ensure_packages()

    # Step 2: Inject simpo_loss implementation
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from utils import inject_simpo_loss
    trainer_path = os.path.join(project_dir, 'scripts', 'simpo_trainer.py')
    inject_simpo_loss(trainer_path)
    print(f"Injected simpo_loss into {trainer_path}")

    # Step 3: Run unit test
    env = os.environ.copy()
    env['PYTHONPATH'] = project_dir + ':' + env.get('PYTHONPATH', '')
    result = subprocess.run(
        [sys.executable, os.path.join(project_dir, 'unit_test', 'unit_test_1.py')],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        raise RuntimeError(f"Unit test failed with return code {result.returncode}")

    # Step 4: Log Python info
    with open(python_info_path, 'w') as f:
        ver_result = subprocess.run([sys.executable, '-VV'], capture_output=True, text=True)
        f.write(ver_result.stdout + ver_result.stderr + '\n---\n')
        freeze_result = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], capture_output=True, text=True)
        f.write(freeze_result.stdout)
    print(f"Python info saved to {python_info_path}")

    # Step 5: Validate output
    from utils import validate_loss_output
    validate_loss_output(output_path)
    print("Task completed successfully.")


if __name__ == '__main__':
    run_simpo_task()
