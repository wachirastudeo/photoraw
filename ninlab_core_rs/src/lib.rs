use pyo3::prelude::*;
use numpy::{PyReadonlyArray3, PyArray1, PyArray3, PyArrayMethods};
use std::collections::HashMap;

mod pipeline;
use pipeline::{process_pipeline, ImageSettings};

#[pyfunction]
#[pyo3(signature = (image, settings, lut=None))]
fn process_image<'py>(
    py: Python<'py>,
    image: PyReadonlyArray3<u8>,
    settings: HashMap<String, f32>,
    lut: Option<Vec<u8>>,
) -> PyResult<Bound<'py, PyArray3<u8>>> {
    let image_view = image.as_array();
    let shape = image_view.shape();
    let height = shape[0];
    let width = shape[1];
    
    // Ensure contiguous array for slice access
    let image_slice = image_view.as_slice().ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err("Input array must be contiguous")
    })?;

    let img_settings = ImageSettings::from_hashmap(&settings);
    let lut_slice = lut.as_deref();

    let output_vec = process_pipeline(image_slice, width, height, &img_settings, lut_slice);

    // Create 1D array and reshape
    // numpy 0.22: PyArray1::from_vec returns Bound<'py, PyArray1<T>>
    let flat_array = PyArray1::from_vec_bound(py, output_vec);
    
    // reshape returns PyResult<Bound<'py, PyArray<T, D>>> or similar
    // Actually, in numpy 0.21/0.22, reshape might return PyResult<Bound<'py, PyArrayDyn<T>>>
    // We need to check the exact API.
    // Assuming flat_array.reshape((h, w, 3)) works.
    let reshaped = flat_array.reshape((height, width, 3))?;
    
    // Convert to PyArray3
    <pyo3::Bound<'_, PyAny> as Clone>::clone(&reshaped).downcast_into().map_err(|_| {
        pyo3::exceptions::PyTypeError::new_err("Failed to cast reshaped array to PyArray3")
    })
}

#[pymodule]
fn ninlab_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_image, m)?)?;
    Ok(())
}
