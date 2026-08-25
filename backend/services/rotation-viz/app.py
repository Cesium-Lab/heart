"""
Rotation Visualizer Backend
Converts between quaternion, rotation matrix, Euler angles, and axis-angle representations.
Run with: python app.py (listens on port 5001)
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import json

app = Flask(__name__)
CORS(app)  # Allow Apache-served frontend to call this


# ─── Core Math ────────────────────────────────────────────────────────────────

def normalize(v):
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("Zero-norm vector cannot be normalized")
    return v / n

def quat_to_rotmat(q, scalar_first=True):
    """q = [w,x,y,z] if scalar_first, else [x,y,z,w]"""
    if not scalar_first:
        q = np.array([q[3], q[0], q[1], q[2]])
    q = normalize(np.array(q, dtype=float))
    w, x, y, z = q
    R = np.array([
        [1 - 2*(y**2 + z**2),   2*(x*y - w*z),       2*(x*z + w*y)],
        [2*(x*y + w*z),         1 - 2*(x**2 + z**2), 2*(y*z - w*x)],
        [2*(x*z - w*y),         2*(y*z + w*x),       1 - 2*(x**2 + y**2)]
    ])
    return R

def rotmat_to_quat(R):
    """Returns [w,x,y,z] scalar-first"""
    R = np.array(R, dtype=float)
    trace = R[0,0] + R[1,1] + R[2,2]
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2,1] - R[1,2]) * s
        y = (R[0,2] - R[2,0]) * s
        z = (R[1,0] - R[0,1]) * s
    elif R[0,0] > R[1,1] and R[0,0] > R[2,2]:
        s = 2.0 * np.sqrt(1.0 + R[0,0] - R[1,1] - R[2,2])
        w = (R[2,1] - R[1,2]) / s
        x = 0.25 * s
        y = (R[0,1] + R[1,0]) / s
        z = (R[0,2] + R[2,0]) / s
    elif R[1,1] > R[2,2]:
        s = 2.0 * np.sqrt(1.0 + R[1,1] - R[0,0] - R[2,2])
        w = (R[0,2] - R[2,0]) / s
        x = (R[0,1] + R[1,0]) / s
        y = 0.25 * s
        z = (R[1,2] + R[2,1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2,2] - R[0,0] - R[1,1])
        w = (R[1,0] - R[0,1]) / s
        x = (R[0,2] + R[2,0]) / s
        y = (R[1,2] + R[2,1]) / s
        z = 0.25 * s
    q = np.array([w, x, y, z])
    if q[0] < 0:
        q = -q  # canonical form: w >= 0
    return normalize(q)

def euler_to_rotmat(angles_deg, sequence='ZYX'):
    """Extrinsic (fixed-frame) rotations. sequence e.g. 'ZYX' means Rz*Ry*Rx."""
    angles = np.radians(angles_deg)
    def Rx(a): return np.array([[1,0,0],[0,np.cos(a),-np.sin(a)],[0,np.sin(a),np.cos(a)]])
    def Ry(a): return np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])
    def Rz(a): return np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])
    mats = {'X': Rx, 'Y': Ry, 'Z': Rz}
    R = np.eye(3)
    for i, axis in enumerate(sequence):
        R = R @ mats[axis](angles[i])
    return R

def rotmat_to_euler(R, sequence='ZYX'):
    """Returns degrees. Handles ZYX (aerospace standard) and others."""
    R = np.array(R, dtype=float)
    if sequence == 'ZYX':
        sy = np.sqrt(R[0,0]**2 + R[1,0]**2)
        singular = sy < 1e-6
        if not singular:
            x = np.degrees(np.arctan2(R[2,1], R[2,2]))
            y = np.degrees(np.arctan2(-R[2,0], sy))
            z = np.degrees(np.arctan2(R[1,0], R[0,0]))
        else:
            x = np.degrees(np.arctan2(-R[1,2], R[1,1]))
            y = np.degrees(np.arctan2(-R[2,0], sy))
            z = 0.0
        return [z, y, x], singular  # Z,Y,X order
    elif sequence == 'XYZ':
        sy = np.sqrt(R[2,2]**2 + R[2,1]**2)
        singular = sy < 1e-6
        if not singular:
            x = np.degrees(np.arctan2(-R[1,2], R[2,2])) if not singular else np.degrees(np.arctan2(R[0,1], R[0,0]))
            y = np.degrees(np.arcsin(R[0,2]))
            z = np.degrees(np.arctan2(-R[0,1], R[0,0]))
        else:
            x = 0.0
            y = np.degrees(np.arcsin(R[0,2]))
            z = np.degrees(np.arctan2(-R[0,1], R[0,0]))
        return [x, y, z], singular
    else:
        # Generic: just do ZYX fallback
        return rotmat_to_euler(R, 'ZYX')

def axis_angle_to_rotmat(axis, angle_deg):
    """Rodrigues' rotation formula"""
    axis = normalize(np.array(axis, dtype=float))
    theta = np.radians(angle_deg)
    K = np.array([
        [0, -axis[2], axis[1]],
        [axis[2], 0, -axis[0]],
        [-axis[1], axis[0], 0]
    ])
    R = np.eye(3) + np.sin(theta) * K + (1 - np.cos(theta)) * K @ K
    return R

def rotmat_to_axis_angle(R):
    """Returns (axis [x,y,z], angle_deg). Angle in [0, 180]."""
    R = np.array(R, dtype=float)
    angle = np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))
    if np.abs(angle) < 1e-8:
        return [0, 0, 1], 0.0
    if np.abs(angle - np.pi) < 1e-6:
        # Special case: symmetric
        diag = np.array([R[0,0], R[1,1], R[2,2]])
        i = np.argmax(diag)
        axis = np.zeros(3)
        axis[i] = np.sqrt((R[i,i] + 1) / 2)
        j, k = (i+1)%3, (i+2)%3
        axis[j] = R[i,j] / (2 * axis[i])
        axis[k] = R[i,k] / (2 * axis[i])
        return axis.tolist(), 180.0
    axis = np.array([R[2,1]-R[1,2], R[0,2]-R[2,0], R[1,0]-R[0,1]]) / (2 * np.sin(angle))
    return normalize(axis).tolist(), float(np.degrees(angle))

def compute_all(R):
    """Given a valid rotation matrix, compute all representations."""
    q = rotmat_to_quat(R)
    euler_zyx, sing_zyx = rotmat_to_euler(R, 'ZYX')
    euler_xyz, sing_xyz = rotmat_to_euler(R, 'XYZ')
    axis, angle = rotmat_to_axis_angle(R)
    return {
        "rotation_matrix": R.tolist(),
        "quaternion_scalar_first": q.tolist(),   # [w,x,y,z]
        "quaternion_scalar_last": [q[1],q[2],q[3],q[0]],  # [x,y,z,w]
        "euler_ZYX_deg": euler_zyx,
        "euler_ZYX_gimbal_lock": bool(sing_zyx),
        "euler_XYZ_deg": euler_xyz,
        "euler_XYZ_gimbal_lock": bool(sing_xyz),
        "axis_angle": {"axis": axis, "angle_deg": angle},
        "det": float(np.linalg.det(R)),
        "is_valid_rotation": bool(
            abs(np.linalg.det(R) - 1.0) < 1e-4 and
            np.allclose(R @ R.T, np.eye(3), atol=1e-4)
        )
    }


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/api/rotation/convert", methods=["POST"])
def convert():
    data = request.get_json()
    source = data.get("source")  # "quaternion", "rotmat", "euler", "axis_angle"

    try:
        if source == "quaternion":
            q = data["quaternion"]  # [w,x,y,z] or [x,y,z,w]
            scalar_first = data.get("scalar_first", True)
            R = quat_to_rotmat(q, scalar_first=scalar_first)

        elif source == "rotmat":
            R = np.array(data["matrix"], dtype=float)
            if R.shape != (3, 3):
                return jsonify({"error": "Matrix must be 3x3"}), 400

        elif source == "euler":
            angles = data["angles_deg"]   # 3 values
            sequence = data.get("sequence", "ZYX")
            R = euler_to_rotmat(angles, sequence)

        elif source == "axis_angle":
            axis = data["axis"]
            angle_deg = data["angle_deg"]
            R = axis_angle_to_rotmat(axis, angle_deg)

        else:
            return jsonify({"error": f"Unknown source: {source}"}), 400

        result = compute_all(R)
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Computation error: {str(e)}"}), 500


@app.route("/api/rotation/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)