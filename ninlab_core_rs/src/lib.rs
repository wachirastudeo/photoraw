use pyo3::prelude::*;
use pyo3::types::PyDict;
use numpy::{PyReadonlyArray3, PyArray1, PyArray3, PyArrayMethods};
use std::collections::HashMap;
use rayon::prelude::*;
use std::fs::File;
use std::io::BufReader;

mod pipeline;
use pipeline::{process_pipeline, ImageSettings};

// ... (process_image and calculate_histogram functions remain unchanged)

/// Read image metadata using Rust (fast & robust for RAW/CR3)
#[pyfunction]
fn read_metadata(py: Python, path: &str) -> PyResult<PyObject> {
    let dict = PyDict::new_bound(py);
    
    // Open file
    let file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return Ok(dict.to_object(py)), 
    };
    
    // Read EXIF with kamadak-exif
    let mut reader = BufReader::new(file);
    let exifreader = exif::Reader::new();
    
    if let Ok(exif) = exifreader.read_from_container(&mut reader) {
        for f in exif.fields() {
            let key = match f.tag {
                exif::Tag::Model => "Camera",
                exif::Tag::Make => "Make",
                exif::Tag::LensModel => "Lens",
                // ISO can be PhotographicSensitivity or ISOSpeedRatings
                exif::Tag::PhotographicSensitivity | exif::Tag::ISOSpeedRatings => "ISO",
                exif::Tag::FNumber => "Aperture",
                exif::Tag::ExposureTime => "Shutter",
                exif::Tag::DateTimeOriginal => "Date",
                _ => continue,
            };
            
            // If the key is already set, don't overwrite (unless it's better?)
            if dict.contains(key)? {
                 continue;
            }

            let val = f.display_value().with_unit(&exif).to_string();
            // Remove quotes for cleaner UI
            let clean_val = val.trim_matches('"').to_string();
            dict.set_item(key, clean_val)?;
        }
    }

    Ok(dict.to_object(py))
}

#[pymodule]
fn ninlab_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_image, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_histogram, m)?)?;
    m.add_function(wrap_pyfunction!(read_metadata, m)?)?;
    Ok(())
}
