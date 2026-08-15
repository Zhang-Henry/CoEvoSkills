import numpy as np

def mask_to_csr(mask):
    """Convert a 2D binary mask to CSR format.
    
    Args:
        mask: 2D numpy array (H, W) with boolean/int values
    
    Returns:
        data: array of True values (all 1s)
        indices: column indices of True pixels
        indptr: row pointer array of length H+1
    """
    h, w = mask.shape
    mask_bool = mask.astype(bool)
    
    indices_list = []
    indptr = [0]
    
    for r in range(h):
        cols = np.where(mask_bool[r])[0]
        indices_list.append(cols)
        indptr.append(indptr[-1] + len(cols))
    
    if indices_list:
        indices = np.concatenate(indices_list) if any(len(c) > 0 for c in indices_list) else np.array([], dtype=np.int32)
    else:
        indices = np.array([], dtype=np.int32)
    
    data = np.ones(len(indices), dtype=np.uint8)
    indptr = np.array(indptr, dtype=np.int32)
    indices = indices.astype(np.int32)
    
    return data, indices, indptr


def save_masks_npz(masks, shape, output_path):
    """Save list of binary masks in CSR format to npz file.
    
    Args:
        masks: list of 2D numpy arrays (H, W)
        shape: tuple (H, W)
        output_path: path to save .npz file
    """
    save_dict = {'shape': np.array(shape)}
    
    for i, mask in enumerate(masks):
        data, indices, indptr = mask_to_csr(mask)
        save_dict[f'f_{i}_data'] = data
        save_dict[f'f_{i}_indices'] = indices
        save_dict[f'f_{i}_indptr'] = indptr
    
    np.savez(output_path, **save_dict)


def load_and_verify_masks(npz_path, num_frames, shape):
    """Load and verify masks from npz file."""
    data = np.load(npz_path)
    
    stored_shape = data['shape']
    assert np.array_equal(stored_shape, shape), f"Shape mismatch: {stored_shape} vs {shape}"
    
    h, w = shape
    for i in range(num_frames):
        d = data[f'f_{i}_data']
        indices = data[f'f_{i}_indices']
        indptr = data[f'f_{i}_indptr']
        
        assert len(indptr) == h + 1, f"Frame {i}: indptr length {len(indptr)} != {h+1}"
        assert len(d) == len(indices), f"Frame {i}: data/indices length mismatch"
        assert indptr[0] == 0, f"Frame {i}: indptr[0] != 0"
        assert indptr[-1] == len(indices), f"Frame {i}: indptr[-1] != len(indices)"
        
        # Check indices are valid columns
        if len(indices) > 0:
            assert np.all(indices >= 0) and np.all(indices < w), \
                f"Frame {i}: indices out of range"
    
    print(f"Verification passed: {num_frames} frames, shape {shape}")
    return True
