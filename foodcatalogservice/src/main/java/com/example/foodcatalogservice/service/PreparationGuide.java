package com.example.foodcatalogservice.service;

import com.example.foodcatalogservice.entity.Dish;
import java.util.ArrayList;
import java.util.List;

/** Method-based preparation aid from actual recipe rows, not a tested recipe. */
public final class PreparationGuide {
    private PreparationGuide() {}
    public static List<String> steps(Dish dish) {
        if (dish.getIngredients()==null || dish.getIngredients().isEmpty() || dish.getCookingMethod()==null) return List.of();
        List<String> steps = new ArrayList<>();
        String quantities = dish.getIngredients().stream()
                .map(i -> i.getIngredient().getNameVi()+": "+i.getRawWeightG().stripTrailingZeros().toPlainString()+" g")
                .collect(java.util.stream.Collectors.joining("; "));
        steps.add("Cân nguyên liệu sống cho một khẩu phần: "+quantities+". Nhân theo số khẩu phần bạn chọn.");
        steps.add("Sơ chế từng loại nguyên liệu riêng; rửa rau củ và cắt thành miếng vừa ăn. Dùng dụng cụ riêng cho nguyên liệu sống và thức ăn đã chín.");
        steps.add(switch(dish.getCookingMethod()) {
            case RAW -> "Dùng nguyên liệu có thể ăn ngay theo hướng dẫn của sản phẩm; không dùng thịt, cá hoặc trứng sống chỉ vì món có nhãn RAW.";
            case BOILED -> "Luộc nguyên liệu cần lâu chín trước, thêm nguyên liệu nhanh chín sau. Kiểm tra phần thực phẩm cần nấu đã chín trước khi dùng.";
            case STEAMED -> "Xếp nguyên liệu vào dụng cụ hấp, đậy nắp và hấp đến khi chín; kiểm tra phần dày nhất trước khi dùng.";
            case STIR_FRIED -> "Dùng lượng dầu theo công thức nếu có. Xào nguyên liệu cần lâu chín trước, thêm rau và nguyên liệu nhanh chín sau; đảo đến khi chín.";
            case PAN_FRIED -> "Dùng lượng dầu theo công thức nếu có, làm nóng chảo rồi áp chảo hai mặt; kiểm tra bên trong đã chín trước khi dùng.";
            case GRILLED -> "Xếp nguyên liệu để nướng chín đều, trở mặt khi cần và kiểm tra phần bên trong. Thời gian/nhiệt độ cụ thể cần theo công thức hoặc thiết bị.";
            case BRAISED -> "Cho nguyên liệu vào nồi với phần nước/gia vị có trong công thức, đun rồi hạ lửa để kho đến khi chín mềm.";
            case SOUP_SIMMERED -> "Cho phần nước và nguyên liệu cần nấu lâu vào nồi trước; ninh ở lửa nhỏ, thêm thịt/rau theo thời gian chín của từng loại và nấu chín trước khi dùng.";
        });
        if (dish.getDiabeticCookingTip()!=null && !dish.getDiabeticCookingTip().isBlank()) steps.add(dish.getDiabeticCookingTip());
        steps.add("Chia thành khẩu phần theo thực đơn. Đây là gợi ý từ nguyên liệu và phương pháp chế biến; danh mục chưa có công thức nấu hoàn chỉnh được kiểm chứng cho món này.");
        return steps;
    }
}
