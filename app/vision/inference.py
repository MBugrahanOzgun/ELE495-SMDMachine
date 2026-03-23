import cv2
import numpy as np
import onnxruntime as ort
from picamera2 import Picamera2

class ResistorDiodeDetectionONNX:

    def __init__(self, capture_index, model_path="best.onnx"):
        self.capture_index = capture_index
        self.imgsz = 640
        self.conf_thres = 0.7
        self.iou_thres = 0.30

        self.session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"]
        )

        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

        print("ONNX Runtime ready (CPU)")

    def preprocess(self, frame):
        self.orig_h, self.orig_w = frame.shape[:2]

        img = cv2.resize(frame, (self.imgsz, self.imgsz))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)

        return img

    def postprocess(self, outputs):
        preds = outputs[0][0].T 

        boxes=[] 
        scores=[]
        class_ids = []

        for p in preds:
            cx, cy, w, h = p[:4]
            class_scores=p[4:]
            
            cls = np.argmax(class_scores)
            conf = class_scores[cls]

            if conf < self.conf_thres:
                continue

            x1 = int((cx - w / 2) * self.orig_w/self.imgsz)
            y1 = int((cy - h / 2) * self.orig_h/self.imgsz)
            x2 = int((cx + w / 2) * self.orig_w/self.imgsz)
            y2 = int((cy + h / 2) * self.orig_h/self.imgsz)

            boxes.append([x1, y1, x2, y2])
            scores.append(float(conf))
            class_ids.append(int(cls))
        print("Detected objects:", len(boxes))
        return boxes, scores, class_ids

    def box_center(self, box):
        x1, y1, x2, y2 = box
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def compute_iou(self, boxA, boxB):
        if boxB is None:
            return 0.0

        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        inter = max(0, xB - xA) * max(0, yB - yA)
        areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

        union = areaA + areaB - inter
        return inter / union if union > 0 else 0.0

    def score_targets(self, target_areas, detected_boxes):
        results = []

        for target in target_areas:
            best_iou = 0.0
            best_box = None

            for box in detected_boxes:
                iou = self.compute_iou(target, box)
                if iou > best_iou:
                    best_iou = iou
                    best_box = box

            results.append({
                "target_box": target,
                "matched_box": best_box,
                "iou_score": best_iou
            })

        return results

    def __call__(self):
        picam2 = Picamera2()
        picam2.configure(picam2.create_preview_configuration(main={"format":"BGR888", "size":(640,640)}))
        picam2.start()

        while True:
            frame = picam2.capture_array()
            inp = self.preprocess(frame)
            outputs = self.session.run(None, {self.input_name: inp})
            outputs = self.session.run(None, {self.input_name: inp})
            boxes, scores, class_ids = self.postprocess(outputs)

            for box, score, cls in zip(boxes, scores, class_ids):
                cv2.rectangle(frame, box[:2], box[2:], (0, 255, 0), 2)
                cv2.putText(
                    frame,
                    f"ID:{cls} {score:.2f}",
                    (box[0], box[1] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1
                )

            target_areas = [
                [150,150, 210, 180],
                [250, 150, 310, 180],
                [150,250, 210, 280],
                [250, 250, 310, 280]
            ]
            for i, t in enumerate(target_areas):
                cv2.rectangle(
                    frame,
                    (t[0], t[1]),
                    (t[2], t[3]),
                    (255, 0, 0),
                    2
                )
                cv2.putText(
                    frame,
                    f"Target {i}",
                    (t[0], t[1] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 0, 0),
                    1
                    )
            scores_iou = self.score_targets(target_areas, boxes)
            for i, s in enumerate(scores_iou):
                print(f"Hedef {i}: IoU = {s['iou_score']:.3f}")

                tx1, ty1, tx2, ty2 = s["target_box"]

                cv2.putText(
                frame,
                f"IoU: {s['iou_score']:.2f}",
                (tx1 + 5, ty1 + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255), 
                1
                )

            cv2.imshow("Resistor-Diode Detection (ONNX)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()


detector = ResistorDiodeDetectionONNX(0)
detector()
